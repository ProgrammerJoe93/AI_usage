import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // [{id, name, plan, limits: [{key, label, short, percent, resetsAt, detail}], error, expired}]
    property var providers: []
    property string errorText: ""
    property bool loading: false
    property double fetchedAt: 0
    property double now: Date.now()

    readonly property string scriptPath: decodeURIComponent(
        Qt.resolvedUrl("../code/fetch_usage.py").toString().replace(/^file:\/\//, ""))
    readonly property var providerIds: ["claude", "codex", "copilot", "antigravity", "opencode"]
    readonly property var panelTags: ({
        claude: "CL", codex: "CX", copilot: "CP", antigravity: "AG", opencode: "OC"
    })
    readonly property var shownProviders: providers.filter(p => p.limits.length > 0)
    readonly property bool hasProblem: errorText !== "" || providers.some(p => p.error)
    readonly property double maxPrimary: shownProviders.reduce(
        (m, p) => Math.max(m, p.limits[0].percent), 0)

    function enabledProviders() {
        const cfg = Plasmoid.configuration;
        const flags = {
            claude: cfg.enableClaude, codex: cfg.enableCodex, copilot: cfg.enableCopilot,
            antigravity: cfg.enableAntigravity, opencode: cfg.enableOpenCode
        };
        return providerIds.filter(id => flags[id]);
    }

    function shellQuote(s) {
        return "'" + String(s).replace(/'/g, "'\\''") + "'";
    }

    function refresh() {
        if (loading) return;
        const ids = enabledProviders();
        if (!ids.length) {
            providers = [];
            errorText = i18n("No providers enabled. Turn some on in the widget settings.");
            return;
        }
        loading = true;
        // Pass the key through the environment so it doesn't show up in `ps`.
        const apiKey = Plasmoid.configuration.opencodeApiKey;
        executable.connectSource((apiKey ? "OPENCODE_API_KEY=" + shellQuote(apiKey) + " " : "")
            + "python3 " + shellQuote(scriptPath)
            + " --providers " + shellQuote(ids.join(","))
            + " --claude-credentials " + shellQuote(Plasmoid.configuration.credentialsPath));
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
        errorText = "";
        // If a provider fails, keep showing its last good numbers next to the error.
        const previous = {};
        providers.forEach(p => previous[p.id] = p);
        providers = (result.providers || []).map(p => {
            if (p.error && !p.limits.length && previous[p.id]) {
                p.limits = previous[p.id].limits;
                p.plan = p.plan || previous[p.id].plan;
                p.stale = true;
            }
            return p;
        });
        if (!providers.length) {
            errorText = i18n("No logged-in AI tools found.");
        }
        fetchedAt = result.fetchedAt || Date.now();
        now = Date.now();
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function planText(plan) {
        if (!plan) return "";
        return String(plan).charAt(0).toUpperCase() + String(plan).slice(1);
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
    Plasmoid.status: maxPrimary >= 90
                     ? PlasmaCore.Types.NeedsAttentionStatus
                     : PlasmaCore.Types.ActiveStatus

    toolTipMainText: i18n("AI Usage")
    toolTipTextFormat: Text.RichText
    toolTipSubText: {
        if (!providers.length) return errorText || i18n("Loading…");
        const lines = [];
        providers.forEach(p => {
            lines.push("<b>" + escapeHtml(p.name) + "</b>"
                       + (p.plan ? " (" + escapeHtml(planText(p.plan)) + ")" : ""));
            p.limits.forEach(l => lines.push(escapeHtml(
                i18n("%1: %2%", l.label, Math.round(l.percent)) + " — " + resetText(l))));
            if (p.error) lines.push(escapeHtml(p.error));
        });
        if (errorText) lines.push(escapeHtml(errorText));
        return lines.join("<br>");
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

        TextMetrics {
            id: shortMetrics
            font: Kirigami.Theme.smallFont
            text: "g7d"
        }

        RowLayout {
            id: compactRow
            anchors.centerIn: parent
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Icon {
                visible: root.hasProblem
                source: "dialog-warning"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }

            PlasmaComponents.Label {
                visible: root.shownProviders.length === 0 && root.errorText === ""
                text: "…"
            }

            Repeater {
                model: root.shownProviders
                delegate: RowLayout {
                    required property var modelData
                    spacing: Kirigami.Units.smallSpacing
                    opacity: modelData.error ? 0.6 : 1

                    PlasmaComponents.Label {
                        visible: root.shownProviders.length > 1
                        text: root.panelTags[modelData.id] || modelData.name
                        font: Kirigami.Theme.smallFont
                        opacity: 0.7
                    }

                    ColumnLayout {
                        spacing: 0
                        Repeater {
                            model: modelData.limits.slice(
                                0, Plasmoid.configuration.showWeeklyInPanel ? 2 : 1)
                            delegate: RowLayout {
                                required property var modelData
                                spacing: Kirigami.Units.smallSpacing

                                PlasmaComponents.Label {
                                    text: modelData.short
                                    font: Kirigami.Theme.smallFont
                                    Layout.minimumWidth: shortMetrics.advanceWidth
                                }
                                MiniBar {
                                    percent: modelData.percent
                                }
                                PlasmaComponents.Label {
                                    text: i18n("%1%", Math.round(modelData.percent))
                                    font: Kirigami.Theme.smallFont
                                    color: root.colorFor(modelData.percent)
                                    horizontalAlignment: Text.AlignRight
                                    Layout.minimumWidth: pctMetrics.advanceWidth
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    fullRepresentation: ColumnLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.preferredWidth: Kirigami.Units.gridUnit * 20
        Layout.preferredHeight: Math.min(Kirigami.Units.gridUnit * 32,
                                         providerColumn.implicitHeight + Kirigami.Units.gridUnit * 5)
        spacing: Kirigami.Units.largeSpacing

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Heading {
                level: 3
                text: i18n("AI Usage")
                Layout.fillWidth: true
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

        PlasmaComponents.ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            PlasmaComponents.ScrollBar.horizontal.policy: PlasmaComponents.ScrollBar.AlwaysOff
            contentWidth: availableWidth

            ColumnLayout {
                id: providerColumn
                width: scroll.availableWidth
                spacing: Kirigami.Units.largeSpacing * 2

                Repeater {
                    model: root.providers
                    delegate: ColumnLayout {
                        id: providerSection
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing

                        Kirigami.Separator {
                            visible: providerSection.index > 0
                            Layout.fillWidth: true
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            Kirigami.Heading {
                                level: 4
                                text: providerSection.modelData.name
                                Layout.fillWidth: true
                            }
                            PlasmaComponents.Label {
                                visible: !!providerSection.modelData.plan
                                text: root.planText(providerSection.modelData.plan)
                                opacity: 0.6
                            }
                        }

                        PlasmaComponents.Label {
                            visible: !!providerSection.modelData.error
                            text: providerSection.modelData.error || ""
                            color: Kirigami.Theme.negativeTextColor
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        Repeater {
                            model: providerSection.modelData.limits
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: Kirigami.Units.smallSpacing
                                opacity: providerSection.modelData.stale ? 0.6 : 1

                                RowLayout {
                                    Layout.fillWidth: true
                                    PlasmaComponents.Label {
                                        text: modelData.label
                                        font.bold: true
                                        elide: Text.ElideRight
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
                                    text: modelData.detail
                                          ? modelData.detail + " · " + root.resetText(modelData)
                                          : root.resetText(modelData)
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.7
                                    wrapMode: Text.Wrap
                                    Layout.fillWidth: true
                                }
                            }
                        }
                    }
                }
            }
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
