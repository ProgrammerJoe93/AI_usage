# AI Usage — KDE Plasma 6 widget

Panel widget showing your AI **subscription** usage limits for:

| Provider       | Limits shown                                                           | Login it reuses                                                                                             |
|----------------|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| Claude         | 5-hour session, weekly (plus Opus/Sonnet weekly if your plan has them) | Claude Code: `~/.claude/.credentials.json`                                                                  |
| Codex          | 5-hour and weekly ChatGPT-plan limits                                  | codex CLI: `~/.codex/auth.json`                                                                             |
| GitHub Copilot | Monthly premium requests (chat/completions on the free plan)           | Copilot CLI (`~/.copilot`, or the keyring via `secret-tool`), the VS Code/neovim plugin, or `gh auth token` |
| Antigravity    | Gemini and Claude/GPT 5-hour and weekly limits                         | The running Antigravity app, IDE or `agy` CLI                                                               |
| OpenCode Go    | 5-hour, weekly and monthly limits                                      | `OPENCODE_API_KEY`, the key in the widget settings, or the `opencode auth login` key                        |

Each provider reuses the login its tool already saved, so there's nothing to set
up apart from OpenCode Go, which needs an opencode API key for exact numbers
(without one it shows an estimate). Checking usage does not use up any of your
quota. Tools that aren't installed or logged in are hidden, and you
can turn providers off in the settings.

## Install

    ./install.sh

Then right-click the panel → *Add Widgets…* → **AI Usage**.

After editing the source, run `./install.sh` again and restart Plasma with
`systemctl --user restart plasma-plasmashell`.

Try it without a panel: `plasmawindowed com.joegineered.aiusage`

## Behaviour

- Panel: the first two limits of each provider, e.g. `CL 5h 34% / 7d 13%`
  (CL = Claude, CX = Codex, CP = Copilot, AG = Antigravity, OC = OpenCode).
  The text turns amber at 70% and red at 90%.
- Click it for progress bars and reset countdowns for every provider.
- It refreshes every 5 minutes by default (you can change this in the settings).
  Right-click → *Refresh* updates it straight away.
- The widget never refreshes OAuth tokens itself, because that would rotate the
  token the tool is using. If a token has expired, the widget says so. Running
  the tool once (`claude`, `codex`, …) refreshes it.
- Antigravity's quota is read from its local language server, so it only updates
  while the Antigravity app, IDE or `agy` is running; otherwise the last values stay
  on screen with a note.
- OpenCode Go without an API key falls back to an estimate made from opencode's
  local history (`~/.local/share/opencode/opencode.db`) and the default Go limits.

## Requirements

`python3` (standard library only) and at least one of the tools above logged in
with a subscription. `secret-tool` (libsecret) is optional, for Copilot CLI
tokens stored in the keyring.
