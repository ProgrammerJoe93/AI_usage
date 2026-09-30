import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_refreshInterval: refreshInterval.value
    property alias cfg_credentialsPath: credentialsPath.text
    property alias cfg_showWeeklyInPanel: showWeekly.checked

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
            text: i18n("Show weekly usage next to session usage")
        }
        QQC2.TextField {
            id: credentialsPath
            Kirigami.FormData.label: i18n("Credentials file:")
            placeholderText: "~/.claude/.credentials.json"
            Layout.fillWidth: true
        }
    }
}
