# Slay the Text

The game is still in alpha, so there are a lot of bugs and weird messages in the game, but you can now play as Ironclad, Silent and Defect.

## 中文版

运行 `python main.py` 即可启动中文界面。游戏保留英文内部标识，因此原有存档和战斗逻辑保持兼容；卡牌、遗物和药水查询支持中文名称，也支持原英文名称。

战斗时，每个回合开始都会由 AI DM 用自然语言播报当前场景、玩家生命/能量、敌人血量和即将执行的动作，不需要选择固定动作，你可以直接输入自然语言，例如：

- `打出猛击`
- `我想先用防御`
- `对左边的敌人使用猛击`
- `使用力量药水`
- `结束回合`

战斗界面现在会按固定面板整合玩家状态、敌人、手牌、药水和操作。出牌或使用药水后，内部过程消息不会全部刷屏，而是由 AI 根据行动前后的真实状态流式整理成一段行动结果；在线请求失败时自动显示本地简短摘要。

有在线模型时，自然语言行动会直接交给模型判断，并要求模型返回受限 JSON 意图，再由本地逻辑校验手牌、药水、目标和能量。例如模型会把“请对右边的敌人使用猛击”转换为 `play_card` 意图，但不会直接执行代码或修改状态。

如果在 pi 环境中启动，游戏会自动读取 pi 的 `PI_PROVIDER`、`PI_MODEL` 和 `~/.pi/agent/models.json` 配置。项目只在运行时读取凭据，不会把密钥写入代码或提交到仓库。

如果要使用其他服务或覆盖当前配置，在 `.env` 中设置：

```dotenv
OPENAI_API_KEY=你的_API_Key
SLAYTHETEXT_AI_EVENTS=1
SLAYTHETEXT_AI_MODEL=gpt-4o-mini
```

也支持 OpenAI 兼容接口：

```dotenv
OPENAI_BASE_URL=https://你的服务地址/v1
```

如果不希望使用 AI 主持和 AI 事件，可以设置 `SLAYTHETEXT_AI_EVENTS=0`。

首次运行需要安装依赖：

```bash
python -m pip install ansimarkup colorama
```

## Download:

## Windows:
https://github.com/Difio3333/slaythetext/releases/download/v0.7/slaythetext.exe
(no Defect in here, clone the repo in order to get them)
## Mac:
https://github.com/Difio3333/slaythetext/releases/download/v0.7/slaythetext
(no Defect in here, clone the repo in order to get them)
## Linux:
I currently don't have an executable but you can just clone the repo and install the dependency "ansimarkup" via 'pip install ansimarkup' and then just run main.py.

# Showcase
You can check out 20 minutes of me talking and playing over the game here (shows an older Version, new Video will come soon):
https://youtu.be/qSctBJB82JI

# Legal Disclaimer

Slay the Spire is a registered trademark by Mega Crit, LLC
Please support the developers of this amazing game on Steam: https://store.steampowered.com/app/646570/Slay_the_Spire/

Additionally the spelling correction code is copied from Peter Norvig. All credit goes to him. You can find the original here: http://norvig.com/spell-correct.html
