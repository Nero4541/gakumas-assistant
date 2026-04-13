"""训练后端适配层，负责把统一配置分发给 SB3 或 RLlib。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname
import importlib.util
import hashlib
import json

from .data import RUNS_DIR
from .service import build_env_from_config
from .auto_training import (
    AutoTrainingConfig,
    DynamicEvaluationScheduler,
    EarlyStoppingCallback,
    analyze_training_progress,
    estimate_total_timesteps,
    extract_evaluation_stats,
    load_training_history,
    make_json_serializable,
    save_training_metadata,
)


@dataclass
class TrainingSpec:
    """训练后端共享的配置对象。"""

    backend: str
    env_config: dict[str, Any]
    total_timesteps: int = 100_000
    checkpoint_freq: int = 10_000
    test_report_freq: int = 0
    eval_freq: int = 10_000
    eval_episodes: int = 5
    rollout_steps: int = 512
    learning_rate: float = 3e-4
    device: str = 'cpu'
    run_dir: str | Path = ''
    auto_resume: bool = False
    seed: int | None = None
    rllib_num_workers: int = 0
    rllib_num_envs_per_worker: int = 1
    rllib_num_gpus: float = 0.0
    rllib_train_batch_size: int = 0
    rllib_minibatch_size: int = 0
    rllib_num_epochs: int = 0
    rllib_rollout_fragment_length: int = 0

    # 自动训练配置
    auto_config: AutoTrainingConfig | None = None
    enable_early_stopping: bool = False
    early_stopping_patience: int = 10
    early_stopping_min_delta: float = 0.01

    # BC 预训练 checkpoint
    pretrained_checkpoint: str | None = None


@dataclass
class TrainingResult:
    """训练完成后返回的关键产物索引。"""

    backend: str
    run_dir: Path
    latest_checkpoint: Path | None
    total_timesteps: int
    evaluation_log: Path | None
    metadata_log: Path | None
    replay_html: Path | None = None
    replay_json: Path | None = None


@dataclass(frozen=True)
class RllibRuntimeConfig:
    """RLlib 训练时使用的有效并行与 batch 配置。"""

    num_env_runners: int
    num_envs_per_env_runner: int
    rollout_fragment_length: int
    train_batch_size: int
    minibatch_size: int
    num_epochs: int


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """把训练过程产物按 JSONL 追加写入磁盘。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(make_json_serializable(payload), ensure_ascii=False) + '\n')


def _safe_save_training_metadata(run_dir: Path, metadata_log: Path, training_metadata: dict[str, Any]) -> None:
    """保存训练元数据；若失败则记录告警但不让训练在收尾阶段崩溃。"""

    try:
        save_training_metadata(run_dir, training_metadata)
    except Exception as exc:
        warning = f'metadata_save_failed: {type(exc).__name__}: {exc}'
        print(f"[TrainingMetadata] Warning: {warning}")
        _append_jsonl(
            metadata_log,
            {
                'kind': 'warning',
                'warning': warning,
                'path': str(run_dir / 'training_metadata.json'),
            },
        )


def _extract_step_from_name(path: Path) -> int:
    """从 checkpoint 文件名中提取步数。"""

    digits = ''.join(char for char in path.stem if char.isdigit())
    return int(digits) if digits else 0


def _latest_checkpoint(directory: Path, pattern: str) -> Path | None:
    """在运行目录中找到最新的 checkpoint。"""

    matches = sorted(directory.glob(pattern), key=lambda item: (_extract_step_from_name(item), item.name))
    return matches[-1] if matches else None


def _coerce_rllib_checkpoint_path(save_result: Any) -> Path:
    """兼容不同 Ray 版本的 save() 返回值，提取真实 checkpoint 路径。"""

    def _to_path(value: str | Path) -> Path:
        if isinstance(value, Path):
            return value
        text = str(value)
        parsed = urlparse(text)
        if parsed.scheme == 'file':
            uri_path = unquote(f'//{parsed.netloc}{parsed.path}' if parsed.netloc else parsed.path)
            return Path(url2pathname(uri_path))
        return Path(text)

    if isinstance(save_result, Path):
        return save_result
    if isinstance(save_result, str):
        return _to_path(save_result)

    checkpoint = getattr(save_result, 'checkpoint', None)
    if checkpoint is not None:
        checkpoint_path = getattr(checkpoint, 'path', None)
        if checkpoint_path:
            return _to_path(checkpoint_path)

    direct_path = getattr(save_result, 'path', None)
    if direct_path:
        return _to_path(direct_path)

    raise TypeError(f'Unsupported RLlib checkpoint save result: {type(save_result)!r}')


def _save_rllib_checkpoint(algo: Any, checkpoint_dir: Path, step: int) -> Path:
    """为 RLlib 统一生成可恢复的 checkpoint_<step> 目录。"""

    target_dir = (checkpoint_dir / f'checkpoint_{int(step):08d}').resolve()
    if hasattr(algo, 'save_to_path'):
        try:
            return _coerce_rllib_checkpoint_path(algo.save_to_path(target_dir.as_uri()))
        except RuntimeError as exc:
            if 'Algorithm.get_state() not supported on the old API stack' not in str(exc):
                raise

    save_fn = getattr(algo, 'save')
    try:
        save_result = save_fn(checkpoint_dir=str(target_dir))
    except TypeError:
        save_result = save_fn(str(target_dir))
    return _coerce_rllib_checkpoint_path(save_result)


def _spec_run_dir(spec: TrainingSpec) -> Path:
    """根据环境配置生成稳定的运行目录。"""

    scenario = str(spec.env_config.get('scenario') or 'scenario')
    mode = str(spec.env_config.get('mode') or 'exam')
    backend = spec.backend
    suffix = hashlib.sha1(json.dumps(spec.env_config, sort_keys=True).encode('utf-8')).hexdigest()[:10]
    base_dir = Path(spec.run_dir) if spec.run_dir else RUNS_DIR
    run_dir = base_dir / f'{backend}_{mode}_{scenario}_{suffix}'
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _fixed_next_artifact_step(latest_step: int, frequency: int) -> int | None:
    """根据固定间隔计算下一次产物落盘/评估步数。"""

    if int(frequency) <= 0:
        return None
    interval = max(int(frequency), 1)
    return ((max(int(latest_step), 0) // interval) + 1) * interval


def _evaluation_env_config(env_config: dict[str, Any], *, seed: int | None = None) -> dict[str, Any]:
    """构造评估专用环境配置，显式关闭训练期随机化。"""

    config = dict(env_config)
    if seed is not None:
        config['seed'] = seed
    config['exam_randomize_context'] = False
    config['exam_randomize_stage_type'] = False
    config['exam_randomize_use_after_item'] = False
    config['exam_stat_jitter_ratio'] = 0.0
    config['exam_score_bonus_jitter_ratio'] = 0.0
    config['exam_starting_stamina_mode'] = 'full'
    return config


def _resolve_dynamic_scheduler(
    spec: TrainingSpec,
    estimated_timesteps: int | None,
    rollout_steps: int,
) -> DynamicEvaluationScheduler | None:
    """为自动训练模式构建动态评估调度器。"""

    if spec.auto_config is None:
        return None
    if not (spec.auto_config.dynamic_eval_schedule or spec.auto_config.dynamic_checkpoint_schedule):
        return None
    return DynamicEvaluationScheduler(
        config=spec.auto_config,
        estimated_total_timesteps=int(estimated_timesteps or spec.total_timesteps),
        rollout_steps=max(int(rollout_steps), 1),
    )


def _format_metric(value: float | None) -> str:
    """把训练日志里的可选指标格式化成短字符串。"""

    if value is None:
        return 'n/a'
    return f'{float(value):.4f}'


def _align_up(value: int, multiple: int) -> int:
    """把数值向上对齐到指定倍数。"""

    if multiple <= 1:
        return max(int(value), 1)
    value = max(int(value), 1)
    return ((value + multiple - 1) // multiple) * multiple


def _resolve_rllib_runtime_config(spec: TrainingSpec) -> RllibRuntimeConfig:
    """根据通用训练参数推导 RLlib 的有效并行与 batch 配置。"""

    num_env_runners = max(int(spec.rllib_num_workers), 0)
    num_envs_per_env_runner = max(int(spec.rllib_num_envs_per_worker), 1)
    rollout_fragment_length = max(
        int(spec.rllib_rollout_fragment_length) or max(int(spec.rollout_steps), 256),
        64,
    )
    sampler_parallelism = max(num_env_runners, 1) * num_envs_per_env_runner
    sample_unit = max(rollout_fragment_length * sampler_parallelism, rollout_fragment_length)

    requested_train_batch_size = int(spec.rllib_train_batch_size)
    if requested_train_batch_size > 0:
        train_batch_size = requested_train_batch_size
    else:
        base_train_batch_size = rollout_fragment_length * sampler_parallelism
        batch_floor = 4_096 if float(spec.rllib_num_gpus) > 0 else (2_048 if sampler_parallelism > 1 else rollout_fragment_length)
        train_batch_size = max(base_train_batch_size, batch_floor)
    train_batch_size = _align_up(max(train_batch_size, rollout_fragment_length), sample_unit)

    requested_minibatch_size = int(spec.rllib_minibatch_size)
    if requested_minibatch_size > 0:
        minibatch_size = min(requested_minibatch_size, train_batch_size)
    else:
        divisor = 4 if float(spec.rllib_num_gpus) > 0 else 8
        default_minibatch_size = max(train_batch_size // divisor, 256)
        minibatch_cap = 2_048 if float(spec.rllib_num_gpus) > 0 else 1_024
        minibatch_size = min(default_minibatch_size, min(minibatch_cap, train_batch_size))

    return RllibRuntimeConfig(
        num_env_runners=num_env_runners,
        num_envs_per_env_runner=num_envs_per_env_runner,
        rollout_fragment_length=rollout_fragment_length,
        train_batch_size=train_batch_size,
        minibatch_size=max(minibatch_size, 1),
        num_epochs=max(int(spec.rllib_num_epochs), 0),
    )


def _set_rllib_config_attr(config: Any, value: Any, *names: str) -> str | None:
    """兼容不同 RLlib 版本的配置字段命名。"""

    for name in names:
        if hasattr(config, name):
            setattr(config, name, value)
            return name
    return None


def _generate_demo_artifacts(
    spec: TrainingSpec,
    checkpoint_path: Path | None,
    run_dir: Path,
    metadata_log: Path,
    *,
    step: int | None = None,
    artifact_kind: str = 'replay',
) -> tuple[Path | None, Path | None]:
    """基于指定 checkpoint 生成一局可视化回放。"""

    mode = str(spec.env_config.get('mode') or 'exam')
    if checkpoint_path is None or mode == 'planning':
        return None, None

    try:
        from .demo_exam import run_demo
    except Exception as exc:
        print(f"[Replay] Skipped automatic replay generation: {exc}")
        return None, None

    scenario = str(spec.env_config.get('scenario') or 'nia_master')
    artifact_step = int(step) if step is not None else _extract_step_from_name(checkpoint_path)
    suffix = artifact_step or 'final'
    output_path = run_dir / 'replays' / f'{artifact_kind}_{spec.backend}_{scenario}_{suffix}.html'
    args = SimpleNamespace(
        checkpoint=checkpoint_path,
        backend=spec.backend,
        scenario=scenario,
        mode=mode,
        stage_type=spec.env_config.get('stage_type'),
        exam_reward_mode=str(spec.env_config.get('exam_reward_mode') or 'score'),
        lesson_action_type=str(spec.env_config.get('lesson_action_type') or ''),
        lesson_level_index=int(spec.env_config.get('lesson_level_index') or 0),
        idol_card_id=str(spec.env_config.get('idol_card_id') or ''),
        producer_level=int(spec.env_config.get('producer_level') or 35),
        idol_rank=int(spec.env_config.get('idol_rank') or 0),
        dearness_level=int(spec.env_config.get('dearness_level') or 0),
        use_after_item=spec.env_config.get('use_after_item'),
        exam_score_bonus_multiplier=spec.env_config.get('exam_score_bonus_multiplier'),
        exam_randomize_context=bool(spec.env_config.get('exam_randomize_context') or False),
        exam_randomize_stage_type=bool(spec.env_config.get('exam_randomize_stage_type') or False),
        exam_randomize_use_after_item=bool(spec.env_config.get('exam_randomize_use_after_item') or False),
        fan_votes=spec.env_config.get('fan_votes'),
        manual_exam_setup=list(spec.env_config.get('manual_exam_setup_paths') or []),
        guarantee_card_effect=list(spec.env_config.get('guarantee_card_effects') or []),
        force_card=list(spec.env_config.get('force_card_groups') or []),
        seed=int(spec.seed if spec.seed is not None else (spec.env_config.get('seed') or 7)),
        max_steps=64,
        output=output_path,
        stochastic=False,
    )
    try:
        report = run_demo(args)
    except Exception as exc:
        print(f"[Replay] Failed to generate automatic replay: {exc}")
        return None, None

    artifacts = report.get('artifacts') or {}
    html_path = Path(str(artifacts.get('html'))) if artifacts.get('html') else None
    json_path = Path(str(artifacts.get('json'))) if artifacts.get('json') else None
    if html_path is not None or json_path is not None:
        _append_jsonl(
            metadata_log,
            {
                'kind': artifact_kind,
                'step': artifact_step,
                'html': str(html_path) if html_path is not None else None,
                'json': str(json_path) if json_path is not None else None,
            },
        )
        print(
            f"[Replay] Generated demo artifacts: html={html_path if html_path is not None else 'n/a'} "
            f"json={json_path if json_path is not None else 'n/a'}"
        )
    return html_path, json_path


def _maybe_generate_demo_artifacts(
    spec: TrainingSpec,
    checkpoint_path: Path | None,
    run_dir: Path,
    metadata_log: Path,
) -> tuple[Path | None, Path | None]:
    """训练结束后为考试模式自动生成一局可视化回放。"""

    return _generate_demo_artifacts(
        spec,
        checkpoint_path,
        run_dir,
        metadata_log,
        step=None,
        artifact_kind='replay',
    )


def _load_bc_pretrained_weights_sb3(model: Any, checkpoint_path: str, device: str = 'cpu') -> None:
    """把 BC 预训练 checkpoint 的权重加载到 SB3 MaskablePPO 的 policy network。"""

    import torch

    bc_state = torch.load(checkpoint_path, map_location=device, weights_only=True)
    bc_weights = bc_state.get('model_state_dict', bc_state)

    # SB3 MultiInputPolicy 的 mlp_extractor + action_net + value_net 结构
    # 与 MaskedPolicyValueNet 不完全对齐，用 strict=False 尽量加载匹配的权重
    policy_state = model.policy.state_dict()
    loaded_keys = []
    for key, value in bc_weights.items():
        if key in policy_state and policy_state[key].shape == value.shape:
            policy_state[key] = value
            loaded_keys.append(key)
    model.policy.load_state_dict(policy_state, strict=False)
    print(f"[BC Pretrain] Loaded {len(loaded_keys)}/{len(bc_weights)} weight tensors into SB3 policy")


def _load_bc_pretrained_weights_rllib(algo: Any, checkpoint_path: str, device: str = 'cpu') -> None:
    """把 BC 预训练 checkpoint 的权重加载到 RLlib 的自定义模型。"""

    import torch

    bc_state = torch.load(checkpoint_path, map_location=device, weights_only=True)
    bc_weights = bc_state.get('model_state_dict', bc_state)

    # RLlib old API stack: algo.get_policy().model.net 是 MaskedPolicyValueNet
    policy = algo.get_policy()
    net = getattr(policy.model, 'net', None)
    if net is None:
        print("[BC Pretrain] Warning: could not find policy.model.net, skipping pretrained weight loading")
        return
    net_state = net.state_dict()
    loaded_keys = []
    for key, value in bc_weights.items():
        if key in net_state and net_state[key].shape == value.shape:
            net_state[key] = value
            loaded_keys.append(key)
    net.load_state_dict(net_state, strict=False)
    print(f"[BC Pretrain] Loaded {len(loaded_keys)}/{len(bc_weights)} weight tensors into RLlib model")


def run_torch_training(spec: TrainingSpec) -> TrainingResult:
    """使用本地 Torch actor-critic 训练器执行轻量训练。"""

    from .trainer import ActorCriticTrainer

    run_dir = _spec_run_dir(spec)
    checkpoint_dir = run_dir / 'checkpoints'
    evaluation_log = run_dir / 'evaluations.jsonl'
    metadata_log = run_dir / 'artifacts.jsonl'
    best_checkpoint = run_dir / 'best_model.pt'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    total_timesteps = int(spec.total_timesteps)
    estimated_timesteps: int | None = None
    if spec.auto_config and spec.auto_config.auto_total_timesteps:
        estimated_timesteps = estimate_total_timesteps(
            spec.env_config,
            min_timesteps=spec.auto_config.min_timesteps,
            max_timesteps=spec.auto_config.max_timesteps,
        )
        if spec.auto_config.full_auto:
            total_timesteps = max(int(spec.auto_config.max_timesteps), total_timesteps)
            schedule_label = 'dynamic' if spec.auto_config.dynamic_eval_schedule else f'fixed:{max(int(spec.eval_freq), 1):,}'
            print(
                f"[AutoConfig] Full auto mode: estimate={estimated_timesteps:,}, min={spec.auto_config.min_timesteps:,}, "
                f"max={spec.auto_config.max_timesteps:,}, eval_schedule={schedule_label}"
            )
        else:
            total_timesteps = estimated_timesteps
            print(f"[AutoConfig] Estimated total timesteps: {estimated_timesteps:,}")

    dynamic_scheduler = _resolve_dynamic_scheduler(spec, estimated_timesteps or total_timesteps, max(int(spec.rollout_steps), 32))
    prior_history = load_training_history(run_dir)

    train_env = build_env_from_config(spec.env_config)
    eval_env = build_env_from_config(_evaluation_env_config(spec.env_config, seed=1000))

    latest_checkpoint = _latest_checkpoint(checkpoint_dir, '*.pt') if spec.auto_resume else None
    trainer = ActorCriticTrainer(
        train_env,
        learning_rate=spec.learning_rate,
        device=spec.device,
        run_dir=run_dir,
    )
    if latest_checkpoint is not None:
        trainer.load_checkpoint(latest_checkpoint)
    elif spec.pretrained_checkpoint:
        trainer.load_model_weights(spec.pretrained_checkpoint, strict=False)

    latest_step = int(trainer.num_timesteps)
    remaining_timesteps = max(total_timesteps - latest_step, 0)

    early_stopping = None
    if spec.enable_early_stopping:
        min_training_steps = spec.auto_config.min_timesteps if spec.auto_config is not None else 0
        early_stopping = EarlyStoppingCallback(
            patience=spec.early_stopping_patience,
            min_delta=spec.early_stopping_min_delta,
            baseline_episodes=spec.eval_episodes,
            min_training_steps=min_training_steps,
            verbose=True,
        )
        print(
            f"[EarlyStopping] Enabled with patience={spec.early_stopping_patience}, "
            f"min_delta={spec.early_stopping_min_delta}, min_steps={min_training_steps:,}"
        )

    evaluation_history = list(prior_history)
    prior_best = [float(item['mean_reward']) for item in evaluation_history if item.get('mean_reward') is not None]
    next_checkpoint = (
        dynamic_scheduler.next_step(latest_step, evaluation_history)
        if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_checkpoint_schedule
        else _fixed_next_artifact_step(latest_step, spec.checkpoint_freq)
    )
    next_eval = (
        dynamic_scheduler.next_step(latest_step, evaluation_history)
        if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_eval_schedule
        else _fixed_next_artifact_step(latest_step, spec.eval_freq)
    )
    next_report = _fixed_next_artifact_step(latest_step, spec.test_report_freq)
    last_checkpoint: Path | None = latest_checkpoint
    best_mean_reward: float | None = max(prior_best) if prior_best else None
    best_checkpoint_path: Path | None = best_checkpoint if best_checkpoint.exists() else None

    if remaining_timesteps > 0:
        print(
            f"[Training] Starting Torch actor-critic: target={total_timesteps:,}, remaining={remaining_timesteps:,}, "
            f"rollout_steps={max(int(spec.rollout_steps), 1):,}"
        )
    else:
        print(f"[Training] No remaining timesteps. target={total_timesteps:,}, latest={latest_step:,}")

    stopped_early = False
    while trainer.num_timesteps < total_timesteps:
        update_steps = min(max(int(spec.rollout_steps), 1), max(total_timesteps - int(trainer.num_timesteps), 0))
        metrics = trainer.train_update(rollout_steps=update_steps)
        current_step = int(trainer.num_timesteps)
        should_stop = False

        while True:
            due_steps = []
            if next_checkpoint is not None and current_step >= next_checkpoint:
                due_steps.append(next_checkpoint)
            if next_eval is not None and current_step >= next_eval:
                due_steps.append(next_eval)
            if next_report is not None and current_step >= next_report:
                due_steps.append(next_report)
            if not due_steps:
                break

            event_step = min(due_steps)
            checkpoint_due = next_checkpoint is not None and event_step == next_checkpoint and current_step >= next_checkpoint
            eval_due = next_eval is not None and event_step == next_eval and current_step >= next_eval
            report_due = next_report is not None and event_step == next_report and current_step >= next_report

            checkpoint_path: Path | None = None
            if checkpoint_due or report_due:
                checkpoint_path = checkpoint_dir / f'step_{event_step}.pt'
                print(f"[Checkpoint] Saving model at step {event_step:,}")
                trainer.save_checkpoint(checkpoint_path)
                last_checkpoint = checkpoint_path
                _append_jsonl(
                    metadata_log,
                    {
                        'kind': 'checkpoint',
                        'step': event_step,
                        'path': str(checkpoint_path),
                        'reason': 'checkpoint_and_report' if checkpoint_due and report_due else ('checkpoint' if checkpoint_due else 'report'),
                        'metrics': metrics,
                    },
                )

            if eval_due:
                print(f"[Evaluation] Running {max(int(spec.eval_episodes), 1)} episodes at step {event_step:,}")
                mean_reward, std_reward = trainer.evaluate(
                    eval_env,
                    episodes=max(int(spec.eval_episodes), 1),
                    deterministic=True,
                    base_seed=1000,
                )
                payload = {
                    'kind': 'evaluation',
                    'step': event_step,
                    'mean_reward': float(mean_reward),
                    'std_reward': float(std_reward),
                    'metrics': metrics,
                }
                evaluation_history.append(payload)
                _append_jsonl(evaluation_log, payload)

                if best_mean_reward is None or mean_reward > best_mean_reward:
                    best_mean_reward = float(mean_reward)
                    best_checkpoint_path = best_checkpoint
                    trainer.save_checkpoint(best_checkpoint)
                    _append_jsonl(
                        metadata_log,
                        {
                            'kind': 'best_checkpoint',
                            'step': event_step,
                            'path': str(best_checkpoint),
                            'mean_reward': float(mean_reward),
                        },
                    )
                    print(f"[Evaluation] New best mean reward: {mean_reward:.4f}")

                if early_stopping is not None:
                    should_stop = early_stopping.on_evaluation(event_step, float(mean_reward), float(std_reward))

            if report_due:
                _generate_demo_artifacts(
                    spec,
                    checkpoint_path or last_checkpoint,
                    run_dir,
                    metadata_log,
                    step=event_step,
                    artifact_kind='test_report',
                )

            if checkpoint_due:
                if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_checkpoint_schedule:
                    next_checkpoint = dynamic_scheduler.next_step(event_step, evaluation_history)
                    print(f"[CheckpointSchedule] Next checkpoint at step {next_checkpoint:,}")
                else:
                    next_checkpoint = event_step + max(spec.checkpoint_freq, 1)

            if eval_due:
                if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_eval_schedule:
                    next_eval = dynamic_scheduler.next_step(event_step, evaluation_history)
                    print(f"[EvaluationSchedule] Next evaluation at step {next_eval:,}")
                else:
                    next_eval = event_step + max(spec.eval_freq, 1)

            if report_due:
                next_report = event_step + max(spec.test_report_freq, 1)

            if should_stop:
                print(f"[EarlyStopping] Stopping training at step {event_step}")
                stopped_early = True
                break

        if should_stop:
            break

    actual_steps = int(trainer.num_timesteps)
    final_checkpoint = checkpoint_dir / f'step_{actual_steps}.pt'
    trainer.save_checkpoint(final_checkpoint)
    _append_jsonl(metadata_log, {'kind': 'checkpoint', 'step': actual_steps, 'path': str(final_checkpoint), 'final': True})

    evaluation_summary = None
    if early_stopping is not None and early_stopping.history:
        evaluation_summary = analyze_training_progress(early_stopping.history)

    training_metadata = {
        'backend': 'torch',
        'total_timesteps': actual_steps,
        'target_timesteps': total_timesteps,
        'estimated_timesteps': estimated_timesteps,
        'dynamic_eval_schedule': bool(spec.auto_config.dynamic_eval_schedule) if spec.auto_config else False,
        'dynamic_checkpoint_schedule': bool(spec.auto_config.dynamic_checkpoint_schedule) if spec.auto_config else False,
        'early_stopped': stopped_early,
        'best_checkpoint': str(best_checkpoint_path) if best_checkpoint_path else None,
        'best_mean_reward': best_mean_reward,
        'env_config': spec.env_config,
    }
    if evaluation_summary is not None:
        training_metadata['evaluation_summary'] = evaluation_summary
    if early_stopping:
        training_metadata['early_stopping_summary'] = early_stopping.get_summary()
    replay_html, replay_json = _maybe_generate_demo_artifacts(spec, final_checkpoint, run_dir, metadata_log)
    if replay_html is not None or replay_json is not None:
        training_metadata['replay_artifacts'] = {
            'html': str(replay_html) if replay_html is not None else None,
            'json': str(replay_json) if replay_json is not None else None,
        }
    _safe_save_training_metadata(run_dir, metadata_log, training_metadata)

    train_env.close()
    eval_env.close()
    return TrainingResult(
        backend='torch',
        run_dir=run_dir,
        latest_checkpoint=final_checkpoint,
        total_timesteps=actual_steps,
        evaluation_log=evaluation_log if evaluation_log.exists() else None,
        metadata_log=metadata_log if metadata_log.exists() else None,
        replay_html=replay_html,
        replay_json=replay_json,
    )


def run_sb3_training(spec: TrainingSpec) -> TrainingResult:
    """使用 Stable-Baselines3 PPO 执行单机调试训练。"""

    try:
        from stable_baselines3 import PPO as SB3PPO
        from stable_baselines3.common.callbacks import BaseCallback
        from stable_baselines3.common.evaluation import evaluate_policy as sb3_evaluate_policy
        from stable_baselines3.common.monitor import Monitor
    except ModuleNotFoundError as exc:
        raise SystemExit('SB3 backend requires stable-baselines3 in the active environment.') from exc

    model_class = SB3PPO
    evaluate_policy = sb3_evaluate_policy
    action_masker = None
    maskable_enabled = False
    try:
        from sb3_contrib import MaskablePPO
        from sb3_contrib.common.maskable.evaluation import evaluate_policy as maskable_evaluate_policy
        from sb3_contrib.common.wrappers import ActionMasker

        model_class = MaskablePPO
        evaluate_policy = maskable_evaluate_policy
        action_masker = ActionMasker
        maskable_enabled = True
    except ModuleNotFoundError:
        print('[SB3] sb3-contrib not installed; falling back to plain PPO without hard action masking. Exam/planning envs expose action_mask in observations, but plain PPO will not enforce it and training quality may degrade badly.')

    def build_monitored_env(eval_seed: int | None = None):
        env_cfg = spec.env_config
        if eval_seed is not None:
            env_cfg = _evaluation_env_config(env_cfg, seed=eval_seed)
        env = build_env_from_config(env_cfg)
        if maskable_enabled and action_masker is not None and hasattr(env, 'action_masks'):
            env = action_masker(env, lambda wrapped_env: wrapped_env.action_masks())
        return Monitor(env)

    run_dir = _spec_run_dir(spec)
    checkpoint_dir = run_dir / 'checkpoints'
    evaluation_log = run_dir / 'evaluations.jsonl'
    metadata_log = run_dir / 'artifacts.jsonl'
    best_checkpoint = run_dir / 'best_model.zip'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    total_timesteps = int(spec.total_timesteps)
    estimated_timesteps: int | None = None
    if spec.auto_config and spec.auto_config.auto_total_timesteps:
        estimated_timesteps = estimate_total_timesteps(
            spec.env_config,
            min_timesteps=spec.auto_config.min_timesteps,
            max_timesteps=spec.auto_config.max_timesteps,
        )
        if spec.auto_config.full_auto:
            total_timesteps = max(int(spec.auto_config.max_timesteps), total_timesteps)
            schedule_label = 'dynamic' if spec.auto_config.dynamic_eval_schedule else f'fixed:{max(int(spec.eval_freq), 1):,}'
            print(
                f"[AutoConfig] Full auto mode: estimate={estimated_timesteps:,}, min={spec.auto_config.min_timesteps:,}, "
                f"max={spec.auto_config.max_timesteps:,}, eval_schedule={schedule_label}"
            )
        else:
            total_timesteps = estimated_timesteps
            print(f"[AutoConfig] Estimated total timesteps: {estimated_timesteps:,}")

    dynamic_scheduler = _resolve_dynamic_scheduler(spec, estimated_timesteps or total_timesteps, max(int(spec.rollout_steps), 32))
    prior_history = load_training_history(run_dir)

    train_env = build_monitored_env()
    eval_env = build_monitored_env(eval_seed=1000)

    latest_checkpoint = _latest_checkpoint(checkpoint_dir, '*.zip') if spec.auto_resume else None
    latest_step = _extract_step_from_name(latest_checkpoint) if latest_checkpoint is not None else 0
    remaining_timesteps = max(total_timesteps - latest_step, 0)

    early_stopping = None
    if spec.enable_early_stopping:
        min_training_steps = spec.auto_config.min_timesteps if spec.auto_config is not None else 0
        early_stopping = EarlyStoppingCallback(
            patience=spec.early_stopping_patience,
            min_delta=spec.early_stopping_min_delta,
            baseline_episodes=spec.eval_episodes,
            min_training_steps=min_training_steps,
            verbose=True,
        )
        print(
            f"[EarlyStopping] Enabled with patience={spec.early_stopping_patience}, "
            f"min_delta={spec.early_stopping_min_delta}, min_steps={min_training_steps:,}"
        )

    if latest_checkpoint is not None:
        model = model_class.load(str(latest_checkpoint), env=train_env, device=spec.device)
    else:
        model = model_class(
            'MultiInputPolicy',
            train_env,
            verbose=1,
            seed=spec.seed,
            device=spec.device,
            n_steps=max(int(spec.rollout_steps), 32),
            learning_rate=spec.learning_rate,
            tensorboard_log=str(run_dir / 'tensorboard'),
        )
        if spec.pretrained_checkpoint:
            _load_bc_pretrained_weights_sb3(model, spec.pretrained_checkpoint, spec.device)

    class PeriodicArtifactCallback(BaseCallback):
        """按计划输出 checkpoint、评估结果和最佳模型。"""

        def __init__(self):
            """根据续训进度初始化产物时点。"""

            super().__init__()
            self.evaluation_history = list(prior_history)
            prior_best = [float(item['mean_reward']) for item in self.evaluation_history if item.get('mean_reward') is not None]
            self.next_checkpoint = (
                dynamic_scheduler.next_step(latest_step, self.evaluation_history)
                if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_checkpoint_schedule
                else _fixed_next_artifact_step(latest_step, spec.checkpoint_freq)
            )
            self.next_eval = (
                dynamic_scheduler.next_step(latest_step, self.evaluation_history)
                if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_eval_schedule
                else _fixed_next_artifact_step(latest_step, spec.eval_freq)
            )
            self.next_report = _fixed_next_artifact_step(latest_step, spec.test_report_freq)
            self.last_checkpoint: Path | None = latest_checkpoint
            self.best_mean_reward: float | None = max(prior_best) if prior_best else None
            self.best_checkpoint: Path | None = best_checkpoint if best_checkpoint.exists() else None

        def _on_step(self) -> bool:
            """在训练步推进时按计划落 checkpoint 并执行评估。"""

            current_step = int(self.model.num_timesteps)
            while True:
                due_steps = []
                if self.next_checkpoint is not None and current_step >= self.next_checkpoint:
                    due_steps.append(self.next_checkpoint)
                if self.next_eval is not None and current_step >= self.next_eval:
                    due_steps.append(self.next_eval)
                if self.next_report is not None and current_step >= self.next_report:
                    due_steps.append(self.next_report)
                if not due_steps:
                    break

                event_step = min(due_steps)
                checkpoint_due = self.next_checkpoint is not None and event_step == self.next_checkpoint and current_step >= self.next_checkpoint
                eval_due = self.next_eval is not None and event_step == self.next_eval and current_step >= self.next_eval
                report_due = self.next_report is not None and event_step == self.next_report and current_step >= self.next_report

                checkpoint_path: Path | None = None
                if checkpoint_due or report_due:
                    checkpoint_path = checkpoint_dir / f'step_{event_step}.zip'
                    print(f"[Checkpoint] Saving model at step {event_step:,}")
                    self.model.save(str(checkpoint_path))
                    self.last_checkpoint = checkpoint_path
                    _append_jsonl(
                        metadata_log,
                        {
                            'kind': 'checkpoint',
                            'step': event_step,
                            'path': str(checkpoint_path),
                            'reason': 'checkpoint_and_report' if checkpoint_due and report_due else ('checkpoint' if checkpoint_due else 'report'),
                        },
                    )

                should_stop = False
                if eval_due:
                    print(f"[Evaluation] Running {max(int(spec.eval_episodes), 1)} episodes at step {event_step:,}")
                    mean_reward, std_reward = evaluate_policy(
                        self.model,
                        eval_env,
                        n_eval_episodes=max(int(spec.eval_episodes), 1),
                        deterministic=True,
                    )
                    payload = {
                        'kind': 'evaluation',
                        'step': event_step,
                        'mean_reward': float(mean_reward),
                        'std_reward': float(std_reward),
                    }
                    self.evaluation_history.append(payload)
                    _append_jsonl(evaluation_log, payload)

                    if self.best_mean_reward is None or mean_reward > self.best_mean_reward:
                        self.best_mean_reward = float(mean_reward)
                        self.best_checkpoint = best_checkpoint
                        self.model.save(str(best_checkpoint))
                        _append_jsonl(
                            metadata_log,
                            {
                                'kind': 'best_checkpoint',
                                'step': event_step,
                                'path': str(best_checkpoint),
                                'mean_reward': float(mean_reward),
                            },
                        )
                        print(f"[Evaluation] New best mean reward: {mean_reward:.4f}")

                    if early_stopping is not None:
                        should_stop = early_stopping.on_evaluation(event_step, float(mean_reward), float(std_reward))

                if report_due:
                    _generate_demo_artifacts(
                        spec,
                        checkpoint_path or self.last_checkpoint,
                        run_dir,
                        metadata_log,
                        step=event_step,
                        artifact_kind='test_report',
                    )

                if checkpoint_due:
                    if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_checkpoint_schedule:
                        self.next_checkpoint = dynamic_scheduler.next_step(event_step, self.evaluation_history)
                        print(f"[CheckpointSchedule] Next checkpoint at step {self.next_checkpoint:,}")
                    else:
                        self.next_checkpoint = event_step + max(spec.checkpoint_freq, 1)

                if eval_due:
                    if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_eval_schedule:
                        self.next_eval = dynamic_scheduler.next_step(event_step, self.evaluation_history)
                        print(f"[EvaluationSchedule] Next evaluation at step {self.next_eval:,}")
                    else:
                        self.next_eval = event_step + max(spec.eval_freq, 1)

                if report_due:
                    self.next_report = event_step + max(spec.test_report_freq, 1)

                if should_stop:
                    print(f"[EarlyStopping] Stopping training at step {event_step}")
                    return False
            return True

    callback = PeriodicArtifactCallback()
    if remaining_timesteps > 0:
        print(
            f"[Training] Starting SB3 PPO: target={total_timesteps:,}, remaining={remaining_timesteps:,}, "
            f"rollout_steps={max(int(spec.rollout_steps), 32):,}, maskable={maskable_enabled}"
        )
        model.learn(total_timesteps=remaining_timesteps, callback=callback, reset_num_timesteps=latest_checkpoint is None, progress_bar=False)
    else:
        print(f"[Training] No remaining timesteps. target={total_timesteps:,}, latest={latest_step:,}")

    actual_steps = int(model.num_timesteps)
    final_checkpoint = checkpoint_dir / f'step_{actual_steps}.zip'
    model.save(str(final_checkpoint))
    _append_jsonl(metadata_log, {'kind': 'checkpoint', 'step': actual_steps, 'path': str(final_checkpoint), 'final': True})

    evaluation_summary = None
    if early_stopping is not None and early_stopping.history:
        evaluation_summary = analyze_training_progress(early_stopping.history)

    training_metadata = {
        'backend': 'sb3',
        'maskable_enabled': maskable_enabled,
        'total_timesteps': actual_steps,
        'target_timesteps': total_timesteps,
        'estimated_timesteps': estimated_timesteps,
        'dynamic_eval_schedule': bool(spec.auto_config.dynamic_eval_schedule) if spec.auto_config else False,
        'dynamic_checkpoint_schedule': bool(spec.auto_config.dynamic_checkpoint_schedule) if spec.auto_config else False,
        'early_stopped': early_stopping.should_stop if early_stopping else False,
        'best_checkpoint': str(callback.best_checkpoint) if callback.best_checkpoint else None,
        'best_mean_reward': callback.best_mean_reward,
        'env_config': spec.env_config,
    }
    if evaluation_summary is not None:
        training_metadata['evaluation_summary'] = evaluation_summary
    if early_stopping:
        training_metadata['early_stopping_summary'] = early_stopping.get_summary()
    replay_html, replay_json = _maybe_generate_demo_artifacts(spec, final_checkpoint, run_dir, metadata_log)
    if replay_html is not None or replay_json is not None:
        training_metadata['replay_artifacts'] = {
            'html': str(replay_html) if replay_html is not None else None,
            'json': str(replay_json) if replay_json is not None else None,
        }
    _safe_save_training_metadata(run_dir, metadata_log, training_metadata)

    return TrainingResult(
        backend='sb3',
        run_dir=run_dir,
        latest_checkpoint=final_checkpoint,
        total_timesteps=actual_steps,
        evaluation_log=evaluation_log if evaluation_log.exists() else None,
        metadata_log=metadata_log if metadata_log.exists() else None,
        replay_html=replay_html,
        replay_json=replay_json,
    )


def run_rllib_training(spec: TrainingSpec) -> TrainingResult:
    """使用 RLlib PPO 执行可多 worker / 多 GPU 的训练。"""

    try:
        import ray
        from ray.rllib.algorithms.ppo import PPOConfig
        from ray.tune.registry import register_env

        from .rllib_model import register_rllib_model
    except ModuleNotFoundError as exc:
        raise SystemExit('RLlib backend requires ray[rllib] in the active environment.') from exc

    run_dir = _spec_run_dir(spec)
    checkpoint_dir = run_dir / 'checkpoints'
    evaluation_log = run_dir / 'evaluations.jsonl'
    metadata_log = run_dir / 'artifacts.jsonl'
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    total_timesteps = int(spec.total_timesteps)
    estimated_timesteps: int | None = None
    if spec.auto_config and spec.auto_config.auto_total_timesteps:
        estimated_timesteps = estimate_total_timesteps(
            spec.env_config,
            min_timesteps=spec.auto_config.min_timesteps,
            max_timesteps=spec.auto_config.max_timesteps,
        )
        if spec.auto_config.full_auto:
            total_timesteps = max(int(spec.auto_config.max_timesteps), total_timesteps)
            schedule_label = 'dynamic' if spec.auto_config.dynamic_eval_schedule else f'fixed:{max(int(spec.eval_freq), 1):,}'
            print(
                f"[AutoConfig] Full auto mode: estimate={estimated_timesteps:,}, min={spec.auto_config.min_timesteps:,}, "
                f"max={spec.auto_config.max_timesteps:,}, eval_schedule={schedule_label}"
            )
        else:
            total_timesteps = estimated_timesteps
            print(f"[AutoConfig] Estimated total timesteps: {estimated_timesteps:,}")

    dynamic_scheduler = _resolve_dynamic_scheduler(spec, estimated_timesteps or total_timesteps, max(int(spec.rollout_steps), 256))
    prior_history = load_training_history(run_dir)

    early_stopping = None
    if spec.enable_early_stopping:
        min_training_steps = spec.auto_config.min_timesteps if spec.auto_config is not None else 0
        early_stopping = EarlyStoppingCallback(
            patience=spec.early_stopping_patience,
            min_delta=spec.early_stopping_min_delta,
            baseline_episodes=spec.eval_episodes,
            min_training_steps=min_training_steps,
            verbose=True,
        )
        print(
            f"[EarlyStopping] Enabled with patience={spec.early_stopping_patience}, "
            f"min_delta={spec.early_stopping_min_delta}, min_steps={min_training_steps:,}"
        )

    env_name = f"gakumas_rl_{hashlib.sha1(json.dumps(spec.env_config, sort_keys=True).encode('utf-8')).hexdigest()[:12]}"
    eval_env_config = _evaluation_env_config(spec.env_config, seed=1000)
    eval_env_name = f"{env_name}_eval"
    register_env(env_name, lambda config: build_env_from_config(config))
    register_env(eval_env_name, lambda config: build_env_from_config(config))
    model_name = register_rllib_model()
    rllib_runtime = _resolve_rllib_runtime_config(spec)

    ray.init(ignore_reinit_error=True, include_dashboard=False)
    try:
        config = (
            PPOConfig()
            .api_stack(enable_rl_module_and_learner=False, enable_env_runner_and_connector_v2=False)
            .environment(env=env_name, env_config=spec.env_config, disable_env_checking=True)
            .framework('torch')
            .training(
                lr=spec.learning_rate,
                train_batch_size=rllib_runtime.train_batch_size,
                model={
                    'custom_model': model_name,
                    'custom_model_config': {'hidden_dim': 256},
                },
            )
            .resources(num_gpus=float(spec.rllib_num_gpus))
            .env_runners(num_env_runners=rllib_runtime.num_env_runners)
            .evaluation(
                evaluation_num_env_runners=0,
                evaluation_duration=max(int(spec.eval_episodes), 1),
                evaluation_duration_unit='episodes',
                evaluation_config={
                    'env': eval_env_name,
                    'env_config': eval_env_config,
                },
            )
        )
        _set_rllib_config_attr(config, rllib_runtime.num_envs_per_env_runner, 'num_envs_per_env_runner')
        _set_rllib_config_attr(config, rllib_runtime.rollout_fragment_length, 'rollout_fragment_length')
        _set_rllib_config_attr(config, 'truncate_episodes', 'batch_mode')
        _set_rllib_config_attr(config, rllib_runtime.minibatch_size, 'minibatch_size', 'sgd_minibatch_size')
        if rllib_runtime.num_epochs > 0:
            _set_rllib_config_attr(config, rllib_runtime.num_epochs, 'num_epochs', 'num_sgd_iter')
        algo = config.build_algo()
        latest_checkpoint = _latest_checkpoint(checkpoint_dir, 'checkpoint*') if spec.auto_resume else None
        latest_step = _extract_step_from_name(latest_checkpoint) if latest_checkpoint is not None else 0
        if latest_checkpoint is not None:
            algo.restore(str(latest_checkpoint))
        elif spec.pretrained_checkpoint:
            _load_bc_pretrained_weights_rllib(algo, spec.pretrained_checkpoint, spec.device)

        evaluation_history = list(prior_history)
        next_checkpoint = (
            dynamic_scheduler.next_step(latest_step, evaluation_history)
            if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_checkpoint_schedule
            else _fixed_next_artifact_step(latest_step, spec.checkpoint_freq)
        )
        next_eval = (
            dynamic_scheduler.next_step(latest_step, evaluation_history)
            if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_eval_schedule
            else _fixed_next_artifact_step(latest_step, spec.eval_freq)
        )
        next_report = _fixed_next_artifact_step(latest_step, spec.test_report_freq)
        total_steps = latest_step
        print(
            f"[Training] Starting RLlib PPO: target={int(total_timesteps):,}, workers={rllib_runtime.num_env_runners:,}, "
            f"envs_per_worker={rllib_runtime.num_envs_per_env_runner:,}, gpus={float(spec.rllib_num_gpus):.1f}, "
            f"fragment={rllib_runtime.rollout_fragment_length:,}, train_batch={rllib_runtime.train_batch_size:,}, "
            f"minibatch={rllib_runtime.minibatch_size:,}, api_stack=old"
        )
        if rllib_runtime.num_epochs > 0:
            print(f"[Training] RLlib PPO epochs={rllib_runtime.num_epochs:,}")
        previous_total_steps = total_steps
        while total_steps < int(total_timesteps):
            result = algo.train()
            total_steps = max(
                total_steps,
                int(result.get('timesteps_total') or 0),
                int(result.get('num_env_steps_sampled_lifetime') or 0),
                int(result.get('num_env_steps_sampled') or 0),
            )
            reward_mean = result.get('episode_reward_mean')
            if reward_mean is None:
                reward_mean = result.get('env_runners', {}).get('episode_return_mean')
            len_mean = result.get('episode_len_mean')
            if len_mean is None:
                len_mean = result.get('env_runners', {}).get('episode_len_mean')
            time_this_iter = float(result.get('time_this_iter_s') or 0.0)
            collected_steps = max(total_steps - previous_total_steps, 0)
            steps_per_sec = (collected_steps / time_this_iter) if time_this_iter > 0 else 0.0
            print(
                f"[Training] iter={int(result.get('training_iteration') or 0):,} steps={total_steps:,} "
                f"reward_mean={_format_metric(float(reward_mean) if reward_mean is not None else None)} "
                f"len_mean={_format_metric(float(len_mean) if len_mean is not None else None)} "
                f"time_this_iter={time_this_iter:.2f}s steps_per_sec={steps_per_sec:.1f}"
            )
            previous_total_steps = total_steps

            while True:
                due_steps = []
                if next_checkpoint is not None and total_steps >= next_checkpoint:
                    due_steps.append(next_checkpoint)
                if next_eval is not None and total_steps >= next_eval:
                    due_steps.append(next_eval)
                if next_report is not None and total_steps >= next_report:
                    due_steps.append(next_report)
                if not due_steps:
                    break

                event_step = min(due_steps)
                checkpoint_due = next_checkpoint is not None and event_step == next_checkpoint and total_steps >= next_checkpoint
                eval_due = next_eval is not None and event_step == next_eval and total_steps >= next_eval
                report_due = next_report is not None and event_step == next_report and total_steps >= next_report

                checkpoint_path: Path | None = None
                if checkpoint_due or report_due:
                    checkpoint_path = _save_rllib_checkpoint(algo, checkpoint_dir, event_step)
                    _append_jsonl(
                        metadata_log,
                        {
                            'kind': 'checkpoint',
                            'step': event_step,
                            'path': str(checkpoint_path),
                            'reason': 'checkpoint_and_report' if checkpoint_due and report_due else ('checkpoint' if checkpoint_due else 'report'),
                        },
                    )
                    latest_checkpoint = checkpoint_path

                should_stop = False
                if eval_due:
                    evaluation = algo.evaluate()
                    mean_reward, std_reward = extract_evaluation_stats(evaluation)
                    payload = {
                        'kind': 'evaluation',
                        'step': event_step,
                        'mean_reward': mean_reward,
                        'std_reward': std_reward,
                        'result': evaluation,
                    }
                    evaluation_history.append(payload)
                    _append_jsonl(evaluation_log, payload)
                    print(
                        f"[Evaluation] step={event_step:,} mean_reward={_format_metric(mean_reward)} "
                        f"std_reward={_format_metric(std_reward)}"
                    )
                    if early_stopping is not None and mean_reward is not None:
                        should_stop = early_stopping.on_evaluation(event_step, float(mean_reward), float(std_reward or 0.0))

                if report_due:
                    _generate_demo_artifacts(
                        spec,
                        checkpoint_path or latest_checkpoint,
                        run_dir,
                        metadata_log,
                        step=event_step,
                        artifact_kind='test_report',
                    )

                if checkpoint_due:
                    if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_checkpoint_schedule:
                        next_checkpoint = dynamic_scheduler.next_step(event_step, evaluation_history)
                        print(f"[CheckpointSchedule] Next checkpoint at step {next_checkpoint:,}")
                    else:
                        next_checkpoint = event_step + max(spec.checkpoint_freq, 1)

                if eval_due:
                    if dynamic_scheduler is not None and spec.auto_config is not None and spec.auto_config.dynamic_eval_schedule:
                        next_eval = dynamic_scheduler.next_step(event_step, evaluation_history)
                        print(f"[EvaluationSchedule] Next evaluation at step {next_eval:,}")
                    else:
                        next_eval = event_step + max(spec.eval_freq, 1)

                if report_due:
                    next_report = event_step + max(spec.test_report_freq, 1)

                if should_stop:
                    print(f"[EarlyStopping] Stopping training at step {event_step}")
                    total_steps = event_step
                    break
            if early_stopping is not None and early_stopping.should_stop:
                break

        final_checkpoint = _save_rllib_checkpoint(algo, checkpoint_dir, int(total_steps))
        _append_jsonl(metadata_log, {'kind': 'checkpoint', 'step': int(total_steps), 'path': str(final_checkpoint), 'final': True})

        training_metadata = {
            'backend': 'rllib',
            'api_stack': 'old',
            'custom_model': model_name,
            'total_timesteps': int(total_steps),
            'target_timesteps': int(total_timesteps),
            'estimated_timesteps': estimated_timesteps,
            'dynamic_eval_schedule': bool(spec.auto_config.dynamic_eval_schedule) if spec.auto_config else False,
            'dynamic_checkpoint_schedule': bool(spec.auto_config.dynamic_checkpoint_schedule) if spec.auto_config else False,
            'early_stopped': early_stopping.should_stop if early_stopping else False,
            'env_config': spec.env_config,
            'rllib_config': {
                'num_env_runners': rllib_runtime.num_env_runners,
                'num_envs_per_env_runner': rllib_runtime.num_envs_per_env_runner,
                'rollout_fragment_length': rllib_runtime.rollout_fragment_length,
                'train_batch_size': rllib_runtime.train_batch_size,
                'minibatch_size': rllib_runtime.minibatch_size,
                'num_epochs': rllib_runtime.num_epochs,
                'num_gpus': float(spec.rllib_num_gpus),
            },
        }
        if early_stopping is not None and early_stopping.history:
            training_metadata['evaluation_summary'] = analyze_training_progress(early_stopping.history)
            training_metadata['early_stopping_summary'] = early_stopping.get_summary()
        replay_html, replay_json = _maybe_generate_demo_artifacts(spec, final_checkpoint, run_dir, metadata_log)
        if replay_html is not None or replay_json is not None:
            training_metadata['replay_artifacts'] = {
                'html': str(replay_html) if replay_html is not None else None,
                'json': str(replay_json) if replay_json is not None else None,
            }
        _safe_save_training_metadata(run_dir, metadata_log, training_metadata)
        return TrainingResult(
            backend='rllib',
            run_dir=run_dir,
            latest_checkpoint=final_checkpoint,
            total_timesteps=int(total_steps),
            evaluation_log=evaluation_log if evaluation_log.exists() else None,
            metadata_log=metadata_log if metadata_log.exists() else None,
            replay_html=replay_html,
            replay_json=replay_json,
        )
    finally:
        ray.shutdown()


def run_training(spec: TrainingSpec) -> TrainingResult:
    """按 backend 分发到对应的训练实现。"""

    if spec.backend == 'torch':
        return run_torch_training(spec)
    if spec.backend == 'sb3':
        if importlib.util.find_spec('stable_baselines3') is None:
            print('[Training] stable-baselines3 not available; falling back to local torch backend.')
            return run_torch_training(replace(spec, backend='torch'))
        return run_sb3_training(spec)
    if spec.backend == 'rllib':
        return run_rllib_training(spec)
    raise ValueError(f'Unsupported backend: {spec.backend}')
