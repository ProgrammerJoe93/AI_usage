import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_refreshInterval: refreshInterval.value
    property alias cfg_credentialsPath: credentialsPath.text
    property alias cfg_showWeeklyInPanel: showWeekly.checked
    property alias cfg_enableClaude: enableClaude.checked
    property alias cfg_enableCodex: enableCodex.checked
    property alias cfg_enableCopilot: enableCopilot.checked
    property alias cfg_enableAntigravity: enableAntigravity.checked
    property alias cfg_enableOpenCode: enableOpenCode.checked
    property alias cfg_opencodeApiKey: opencodeApiKey.text

    Kirigami.FormLayout {
        QQC2.SpinBox {
            id: refreshInterval
            Kirigami.FormData.label: i18n("Refresh every (minutes):")
            from: 1
            to: 120
        }
        QQC2.CheckBox {
            id: showWeekly
            Kirigami.FormData.label: i18n("Panel:")
            text: i18n("Show the second limit (usually weekly) under the first")
        }

        Item {
            Kirigami.FormData.isSection: true
        }

        QQC2.CheckBox {
            id: enableClaude
            Kirigami.FormData.label: i18n("Providers:")
            text: i18n("Claude")
        }
        QQC2.CheckBox {
            id: enableCodex
            text: i18n("Codex (ChatGPT plan)")
        }
        QQC2.CheckBox {
            id: enableCopilot
            text: i18n("GitHub Copilot")
        }
        QQC2.CheckBox {
            id: enableAntigravity
            text: i18n("Antigravity")
        }
        QQC2.CheckBox {
            id: enableOpenCode
            text: i18n("OpenCode Go")
        }
        QQC2.Label {
            text: i18n("Tools that aren't installed or logged in are hidden.")
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        Item {
            Kirigami.FormData.isSection: true
        }

        QQC2.TextField {
            id: credentialsPath
            Kirigami.FormData.label: i18n("Claude credentials file:")
            placeholderText: "~/.claude/.credentials.json"
            Layout.fillWidth: true
        }
        Kirigami.PasswordField {
            id: opencodeApiKey
            Kirigami.FormData.label: i18n("OpenCode API key:")
            placeholderText: i18n("From opencode login")
            Layout.fillWidth: true
        }
    }
}
