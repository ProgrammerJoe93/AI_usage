import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    property var limits: []
    property string plan: ""
    property string errorText: ""
    property bool loading: false
    property double fetchedAt: 0
    property double now: Date.now()

    readonly property string scriptPath: decodeURIComponent(
        Qt.resolvedUrl("../code/fetch_usage.py").toString().replace(/^file:\/\//, ""))
    readonly property var session: findLimit("five_hour")
    readonly property var weekly: findLimit("seven_day")

    function findLimit(key) {
        for (let i = 0; i < limits.length; i++) {
            if (limits[i].key === key) return limits[i];
        }
        return null;
    }

    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function refresh() {
        if (loading) return;
        loading = true;
        executable.connectSource("python3 " + shellQuote(scriptPath) + " "
                                 + shellQuote(Plasmoid.configuration.credentialsPath));
    }

    function handleOutput(stdout, stderr) {
        loading = false;
        let result;
        try {
            result = JSON.parse(stdout);
        } catch (e) {
            errorText = i18n("Helper failed: %1", (stderr || stdout || "no output").trim());
            return;
        }
        if (result.error) {
            errorText = result.error;
            return;
        }
        errorText = "";
        limits = result.limits || [];
        plan = result.plan || "";
        fetchedAt = result.fetchedAt || Date.now();
        now = Date.now();
    }

    function colorFor(pct) {
        if (pct >= 90) return Kirigami.Theme.negativeTextColor;
        if (pct >= 70) return Kirigami.Theme.neutralTextColor;
        return Kirigami.Theme.textColor;
    }

    function formatDuration(ms) {
        if (ms <= 0) return i18n("now");
        const mins = Math.floor(ms / 60000);
        const d = Math.floor(mins / 1440);
        const h = Math.floor((mins % 1440) / 60);
        const m = mins % 60;
        if (d > 0) return i18n("%1d %2h", d, h);
        if (h > 0) return i18n("%1h %2m", h, m);
        return i18n("%1m", m);
    }

    function resetText(limit) {
        if (!limit || !limit.resetsAt) return i18n("No reset scheduled");
        const when = new Date(limit.resetsAt);
        const fmt = (limit.resetsAt - now) > 86400000 ? "ddd hh:mm" : "hh:mm";
        return i18n("Resets in %1 (%2)", formatDuration(limit.resetsAt - now),
                    Qt.formatDateTime(when, fmt));
    }

    Plasmoid.icon: "utilities-system-monitor"
    Plasmoid.status: session && session.percent >= 90
                     ? PlasmaCore.Types.NeedsAttentionStatus
                     : PlasmaCore.Types.ActiveStatus

    toolTipMainText: i18n("AI Usage")
    toolTipSubText: {
        if (!limits.length) return errorText || i18n("Loading…");
        const lines = limits.map(l => i18n("%1: %2%", l.label, Math.round(l.percent))
                                      + " — " + resetText(l));
        if (errorText) {
            lines.push(i18n("Last updated %1 — %2",
                            Qt.formatDateTime(new Date(fetchedAt), "hh:mm"), errorText));
        }
        return lines.join("\n");
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh")
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        }
    ]

    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: (sourceName, data) => {
            disconnectSource(sourceName);
            root.handleOutput(data["stdout"], data["stderr"]);
        }
    }

    Timer {
        interval: Math.max(1, Plasmoid.configuration.refreshInterval) * 60000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Timer {
        // Keeps the "resets in" countdowns current between fetches.
        interval: 30000
        running: true
        repeat: true
        onTriggered: root.now = Date.now()
    }

    function barColor(pct) {
        if (pct >= 90) return Kirigami.Theme.negativeTextColor;
        if (pct >= 70) return Kirigami.Theme.neutralTextColor;
        return Kirigami.Theme.highlightColor;
    }

    component MiniBar: Rectangle {
        property real percent: 0

        implicitWidth: Kirigami.Units.gridUnit * 2.5
        implicitHeight: Math.max(3, Math.round(Kirigami.Units.smallSpacing * 1.25))
        radius: height / 2
        color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g,
                       Kirigami.Theme.textColor.b, 0.2)

        Rectangle {
            width: parent.width * Math.min(100, Math.max(0, parent.percent)) / 100
            height: parent.height
            radius: parent.radius
            color: root.barColor(parent.percent)
        }
    }

    compactRepresentation: MouseArea {
        id: compact

        Layout.minimumWidth: compactRow.implicitWidth
        Layout.preferredWidth: compactRow.implicitWidth
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded

        TextMetrics {
            id: pctMetrics
            font: Kirigami.Theme.smallFont
            text: "100%"
        }

        RowLayout {
            id: compactRow
            anchors.centerIn: parent
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                visible: root.errorText !== ""
                source: "dialog-warning"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }

            PlasmaComponents.Label {
                visible: root.session === null && root.errorText === ""
                text: "…"
            }

            GridLayout {
                visible: root.session !== null
                opacity: root.errorText === "" ? 1 : 0.6
                columns: 3
                rowSpacing: 0
                columnSpacing: Kirigami.Units.smallSpacing

                PlasmaComponents.Label {
                    text: i18n("5h")
                    font: Kirigami.Theme.smallFont
                }
                MiniBar {
                    percent: root.session ? root.session.percent : 0
                }
                PlasmaComponents.Label {
                    text: root.session ? i18n("%1%", Math.round(root.session.percent)) : ""
                    font: Kirigami.Theme.smallFont
                    color: root.session ? root.colorFor(root.session.percent) : Kirigami.Theme.textColor
                    horizontalAlignment: Text.AlignRight
                    Layout.minimumWidth: pctMetrics.advanceWidth
                }

                PlasmaComponents.Label {
                    visible: weeklyBar.visible
                    text: i18n("7d")
                    font: Kirigami.Theme.smallFont
                }
                MiniBar {
                    id: weeklyBar
                    visible: Plasmoid.configuration.showWeeklyInPanel && root.weekly !== null
                    percent: root.weekly ? root.weekly.percent : 0
                }
                PlasmaComponents.Label {
                    visible: weeklyBar.visible
                    text: root.weekly ? i18n("%1%", Math.round(root.weekly.percent)) : ""
                    font: Kirigami.Theme.smallFont
                    color: root.weekly ? root.colorFor(root.weekly.percent) : Kirigami.Theme.textColor
                    horizontalAlignment: Text.AlignRight
                    Layout.minimumWidth: pctMetrics.advanceWidth
                }
            }
        }
    }

    fullRepresentation: ColumnLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.preferredWidth: Kirigami.Units.gridUnit * 20
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Heading {
                level: 3
                text: i18n("AI Usage")
                Layout.fillWidth: true
            }
            PlasmaComponents.Label {
                visible: root.plan !== ""
                text: root.plan.charAt(0).toUpperCase() + root.plan.slice(1)
                opacity: 0.6
            }
            PlasmaComponents.ToolButton {
                icon.name: "view-refresh"
                enabled: !root.loading
                onClicked: root.refresh()
                PlasmaComponents.ToolTip.text: i18n("Refresh now")
                PlasmaComponents.ToolTip.visible: hovered
            }
        }

        PlasmaComponents.Label {
            visible: root.errorText !== ""
            text: root.errorText
            color: Kirigami.Theme.negativeTextColor
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        Repeater {
            model: root.limits
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true
                    PlasmaComponents.Label {
                        text: modelData.label
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    PlasmaComponents.Label {
                        text: i18n("%1% used", Math.round(modelData.percent))
                        color: root.colorFor(modelData.percent)
                    }
                }
                PlasmaComponents.ProgressBar {
                    from: 0
                    to: 100
                    value: Math.min(100, modelData.percent)
                    Layout.fillWidth: true
                }
                PlasmaComponents.Label {
                    text: root.resetText(modelData)
                    font: Kirigami.Theme.smallFont
                    opacity: 0.7
                }
            }
        }

        Item {
            Layout.fillHeight: true
        }

        PlasmaComponents.Label {
            visible: root.fetchedAt > 0
            text: i18n("Updated %1", Qt.formatDateTime(new Date(root.fetchedAt), "hh:mm:ss"))
            font: Kirigami.Theme.smallFont
            opacity: 0.5
            Layout.alignment: Qt.AlignRight
        }
    }
}
