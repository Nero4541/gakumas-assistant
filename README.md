<p align="center">
  <img alt="LOGO" src="./assets/images/gakumas_logo.png" width="256" height="256" style="background: white" />
</p>

<div align="center">

# Gakumas Assistant
一个基于 **YOLO + OCR** 的《学园偶像大师》自动化辅助工具  
✨ 如果喜欢 Gakumas Assistant，欢迎在项目右上角点亮 Star 支持 ✨
</div>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white">
  <img alt="platform" src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux">
  <img alt="Yolo" src="https://img.shields.io/badge/Yolo-v11-blue">
  <br>
  <img alt="license" src="https://img.shields.io/github/license/Pigeon-Server/gakumas-assistant">
  <img alt="commit" src="https://img.shields.io/github/commit-activity/m/Pigeon-Server/gakumas-assistant">
  <img alt="stars" src="https://img.shields.io/github/stars/Pigeon-Server/gakumas-assistant?style=social">
  <img alt="downloads" src="https://img.shields.io/github/downloads/Pigeon-Server/gakumas-assistant/total?style=social">
</p>

![](./docs/webui.png)

## 功能列表
### 目前已实现
> - 进入游戏
>   - 自动更新游戏
> - 领取活动费
> - 每日派遣
>   - 重新选择任务时长
> - 自动领取邮箱礼物
> - 自动领取任务奖励
> - 自动领取月卡奖励
> - 自动购买每日商店
>   - 自动学习物品信息
> - 自动竞技场
> 
### 待实现/待完善：
> - 工具框架
>   - 任务错误回退
> - 完善任务
> - 新竞技场
> - 自动P卡

## 注意事项
> 大部分测试都是在 `Windows` 系统上测试的，因此其他操作系统若有运行问题，请提 Issues 或加群讨论。  

> 安卓模拟器开发是基于 `MuMu12` 模拟器测试的，因此推荐使用 MuMu12 运行游戏。 其他模拟器若出现问题，请第一时间把脚本根目录下`logs`最新的日志文件上传并截图进行反馈。

> 汉化版本暂不支持，请关闭汉化插件后使用

> 本项目使用 `Yolov11n` 模型进行图像识别，请确保电脑有显卡且支持[DirectML](https://learn.microsoft.com/zh-cn/windows/ai/directml/dml)，否则将会回退到CPU推理，可能会导致效率低下。

## 安装
前往 [Releases](https://github.com/Pigeon-Server/gakumas-assistant/releases) 下载打包后的文件   
运行 `Gakumas Assistant.exe`  
更多使用说明参见 [使用手册](./docs/use_script.md)  

## 免责声明
**请在使用本项目前仔细阅读以下内容。使用本脚本将带来包括但不限于账号被封禁的风险。**

### 总则
本项目是一个为游戏 **《学园偶像大师》（学園アイドルマスター）** 设计的自动操作脚本。本项目的创建目的仅为技术学习与研究，并非为了提供商业服务或鼓励不正当的游戏行为。

### 版权声明
本项目所使用的部分资源文件，包括但不限于图像、音频、模型等，其版权归属于其原始权利人。该游戏的开发商为 **QualiArts**，发行商为**万代南梦宫娱乐（Bandai Namco Entertainment Inc.）**。

1.  **权利归属**：本项目中使用的所有相关游戏资源文件的版权、商标权及其他一切知识产权，均归 **QualiArts**、**万代南梦宫娱乐**或其相关权利方所有。

2.  **非官方性质**：本项目为非官方、非商业性质的开源项目。本项目的开发者与 **QualiArts** 及 **万代南梦宫娱乐**没有任何形式的关联、合作或官方授权。

### 核心风险与责任限制
1.  **账号封禁风险**：**您必须清楚地认识到，使用任何形式的第三方自动操作脚本（包括本项目）都有违反《学园偶像大师》的用户协议（利用規約）的潜在风险。游戏运营商有权对使用此类脚本的账号采取惩罚措施，包括但不限于临时或永久封禁账号。对于因使用本脚本而导致的任何账号损失（如封号、数据回滚等），项目作者概不负责。**

> ・对本服务的服务器等进行非法访问、窃取数据、使用使软件进行非法处理的程序、使用工具等获取信息或使用工具等不正当推进游戏的行为。

> ・本サービスのサーバー等への不正アクセス行為、データ窃取行為、ソフトウェアに不正な処理を行わせるプログラムを使用する行為、ツール等を使用して情報を取得する行為またはツール等を使用して不正にゲームを有利に進める行為

2. **使用限制**：本项目的全部内容**严禁用于任何商业用途或恶意破坏游戏平衡的行为**。任何将本项目用于此类活动的行为，均可能构成对版权方的侵权和对游戏运营商的违约，由此产生的一切法律责任由使用者自行承担。

3. **无担保与责任限制**：本项目按“原样”提供，不附带任何形式的明示或暗示担保，包括其功能的稳定性、准确性或持续可用性。对于因使用或无法使用本项目而导致的任何直接、间接、偶然、特殊或继发性损害（**包括但不限于账号封禁**），项目作者概不负责。

**继续下载、安装或使用本项目，即表示您已完全阅读、理解并同意承担以上所有风险和条款。如果您不同意，请立即停止使用并删除本项目的所有相关文件。**

## 开发
**安装环境**
```bash
python3 -m pip install -r requirements.dev.txt
# 中国大陆网络可以使用 requirements.dev.cn.txt
```
**拉取子模块**
```bash
git submodule init
git submodule update
```
**YOLO检测模型训练**  
#### 训练：
该项目基于 YOLO v11，并使用了两个独立模型，分别负责主界面识别与训练界面识别。训练脚本位于 train/<model_name>/train.py。

- BaseUI 模型：使用约 4.1K 张有效样本训练，用于主 UI 的目标检测。
- Producer 模型：使用约 2K 张样本训练，用于训练界面的检测任务。

两个模型均根据其应用场景独立优化，以获得更高的识别精度和更稳定的推理效果。
#### 数据集：
> 待脱敏后开放，如有需要请联系**skyfsj@qq.com**

## 许可证
Copyright © 2020-2025 Pigeon Server Team, All rights reserved.

Licensed under The GNU General Public License version 3 (GPLv3) (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

https://www.gnu.org/licenses/gpl-3.0.html

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.

### 致谢
本项目主要用到了以下开源项目，感谢各位开发者的付出：
- **[GkmasObjectManager](https://github.com/AllenHeartcore/GkmasObjectManager)**  
游戏资源提取器
- **[gakumasu-diff](https://github.com/vertesan/gakumasu-diff)**  
游戏数据
- **[GakumasTranslationData](https://github.com/chinosk6/GakumasTranslationData.git)**  
游戏文本翻译