# AI Usage — KDE Plasma 6 widget

Panel widget showing your Claude **subscription** usage: the current 5-hour
session and the weekly limits (plus Opus/Sonnet weekly limits if your plan has them).

No API key is needed. It reuses the OAuth login token that Claude Code saves in
`~/.claude/.credentials.json` and calls the same usage endpoint as Claude Code's
`/usage` command. Checking usage does not use up any of your quota.

## Install

    ./install.sh

Then right-click the panel → *Add Widgets…* → **AI Usage**.

After editing the source, run `./install.sh` again and restart Plasma with
`systemctl --user restart plasma-plasmashell`.

Try it without a panel: `plasmawindowed com.joegineered.aiusage`

## Behaviour

- Panel: `5h 34%  7d 13%`. The text turns amber at 70% and red at 90%.
- Click it for progress bars and reset countdowns.
- It refreshes every 5 minutes by default (you can change this in the settings).
  Right-click → *Refresh* updates it straight away.
- The widget never refreshes the OAuth token itself, because doing that would
  rotate the token Claude Code is using. If the token has expired, the widget
  says so. Running `claude` once refreshes it.

## Requirements

`python3` (standard library only) and Claude Code logged in with a Pro/Max/Team account.
