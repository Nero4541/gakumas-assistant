"""LLM 决策模块 — 基于大语言模型的培育策略系统。

模块结构:
  config.py          — LLM 配置（从 ConfigService 读取）
  client.py          — OpenAI API 客户端封装
  strategy.py        — 统一决策入口
  state_extractor.py — 游戏状态提取（YOLO/OCR/CLIP → 结构化数据）
  prompt_builder.py  — Jinja2 提示词渲染
  prompts/           — 提示词模板文件
"""
