# image2-gen-skill

`image2-gen-skill` 是一个 AI Agent 图像生成技能，当前脚本只支持 `gpt-image-2` 字段：

- 文生图：调用 `<baseurl>/images/generations`
- 图生图 / 改图：调用 `<baseurl>/images/edits`

执行前会先优化提示词：保留用户核心主体和原意，补充光影、构图、画质、风格等细节，再调用脚本。

## 复制给 Agent 安装 / 更新

安装时复制给 Agent：

```text
请帮我安装这个 AI Agent 技能：
https://github.com/SilenceSu/image2-gen-skill.git

请根据当前 Agent / 客户端的技能目录规则安装。
如果是 Codex，可以安装到：
- Windows: %USERPROFILE%\.codex\skills\image2-gen-skill
- Linux / macOS: ~/.codex/skills/image2-gen-skill

如果目录已存在，请不要覆盖，改为进入目录执行 git pull 更新。
安装后检查 SKILL.md、scripts/generate_image.py、scripts/edit_image.py 是否存在。
不要替我写入真实 token，接口配置由我自己放到 ~/.config/image2-gen/config.json。
```

更新时复制给 Agent：

```text
请帮我更新 image2-gen-skill：
https://github.com/SilenceSu/image2-gen-skill.git

请找到当前 Agent / 客户端的技能安装目录里的 image2-gen-skill 文件夹。
如果该目录是 git 仓库，请进入目录执行 git pull。
如果目录不存在，请按当前 Agent 的技能目录规则从上面的仓库安装。
如果目录存在但不是 git 仓库，请先询问我是否重新安装，不要直接覆盖。

更新后检查 SKILL.md、scripts/generate_image.py、scripts/edit_image.py 是否存在。
不要修改 ~/.config/image2-gen/config.json，不要覆盖 baseurl、token、model。
```

## 配置

配置文件：

```text
~/.config/image2-gen/config.json
```

Windows 通常是：

```text
C:\Users\<用户名>\.config\image2-gen\config.json
```

示例：

```json
{
  "baseurl": "https://your-image-api.example.com/v1",
  "token": "<api-token>",
  "model": "gpt-image-2"
}
```

说明：

- `baseurl` 要包含 `/v1`。
- `model` 可省略，默认是 `gpt-image-2`，脚本只接受这个模型。
- 不要把真实 token 写进 README、日志或公开内容。

## 使用

触发技能：

```text
$image2-gen-skill 帮我生成一张热血传奇攻沙背景，主角是道士和狗
```

自然描述也可以：

```text
帮我文生图：一个道士带着狗在攻沙
帮我图生图，参考 D:\path\to\input.png，把它改成传奇攻沙风格
```

直接运行脚本：

```powershell
python .\scripts\generate_image.py --prompt "一个道士带着神兽在攻沙战场中冲锋" --size 1536x1024 --quality high --output-dir "output\imagegen\mir-siege"
```

```powershell
python .\scripts\edit_image.py --image "D:\path\to\reference.png" --prompt "保留主体，把背景改成攻沙战场" --size 1024x1536 --quality high --output-dir "output\imagegen\edit-mir-siege"
```

## 输出

默认输出目录：

```text
image2_outputs/
```

建议任务输出目录：

```text
output\imagegen\<任务名>\
```

脚本会保存：

```text
image_1.png
response.json
```

图生图流向：

```text
本地输入图 -> edit_image.py -> <baseurl>/images/edits -> 输出目录
```

## 备注

- 支持输入图格式：PNG、JPG、JPEG、WebP。
- 模型优先级：命令行 `--model` > 配置文件 `model` > `gpt-image-2`，但最终只能是 `gpt-image-2`。
- 常用字段：`size`、`quality`、`background`、`output_format`、`output_compression`、`moderation`、`user`；图生图额外支持 `mask` 和最多 16 张 `image`。
- `token_configured` 只是安全检查显示用的布尔值，不是配置字段。
