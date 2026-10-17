import QtQuick
import QtQuick.Layouts
import Dogear
import "../components"

DgDialog {
    id: dialog
    objectName: "aboutDialog"
    width: Math.min(parent ? parent.width - 2 * Theme.spaceHuge : 560, 40 * Theme.fontBody)

    property bool showLicense: false
    onOpened: showLicense = false

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.spaceXl
        Image {
            source: AppInfo.icon
            sourceSize: Qt.size(Theme.fontDisplay * 2.5, Theme.fontDisplay * 2.5)
            Layout.preferredWidth: Theme.fontDisplay * 2.5
            Layout.preferredHeight: Theme.fontDisplay * 2.5
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.spaceXs
            DgText { text: AppInfo.name; role: "display"; font.weight: Font.Bold }
            DgText {
                Layout.fillWidth: true
                text: AppInfo.tagline
                secondary: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
            }
            DgText { text: "Version " + AppInfo.version; muted: true; role: "small" }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        Layout.topMargin: Theme.spaceLg
        columns: 2
        columnSpacing: Theme.spaceXl
        rowSpacing: Theme.spaceMd

        DgText { text: "Made by"; muted: true; role: "small" }
        DgText { text: AppInfo.organization }

        DgText { text: "Created"; muted: true; role: "small" }
        DgText { text: AppInfo.created }

        DgText { text: "License"; muted: true; role: "small" }
        RowLayout {
            spacing: Theme.spaceLg
            DgText { text: AppInfo.license + ", " + AppInfo.copyright }
            DgButton {
                objectName: "aboutLicense"
                text: dialog.showLicense ? "Hide" : "Read it"
                variant: "ghost"
                onClicked: dialog.showLicense = !dialog.showLicense
            }
        }

        DgText { text: "Support"; muted: true; role: "small" }
        RowLayout {
            spacing: Theme.spaceLg
            DgText { text: AppInfo.supportEmail }
            DgButton {
                text: "Email"
                variant: "ghost"
                onClicked: Qt.openUrlExternally("mailto:" + AppInfo.supportEmail + "?subject="
                    + encodeURIComponent("Dogear " + AppInfo.version) + "&body="
                    + encodeURIComponent("\n\n--\n" + AppInfo.details))
            }
            DgButton {
                text: "Copy"
                variant: "ghost"
                onClicked: AppInfo.copy(AppInfo.supportEmail)
            }
        }

        DgText { text: "Privacy"; muted: true; role: "small"; Layout.alignment: Qt.AlignTop }
        DgText {
            Layout.fillWidth: true
            text: "No accounts, no telemetry, no network access. Your PDFs are never changed, and your "
                + "marks stay in your library folder."
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }

        DgText { text: "Built with"; muted: true; role: "small" }
        DgText {
            Layout.fillWidth: true
            text: "Qt " + AppInfo.qtVersion + " and Qt PDF, PySide6 " + AppInfo.pysideVersion
                + ", Python " + AppInfo.pythonVersion
            secondary: true
            wrapMode: Text.WordWrap
            elide: Text.ElideNone
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 14 * Theme.fontSmall
        visible: dialog.showLicense
        color: Theme.bgSunken
        radius: Theme.radius
        border.width: Theme.borderWidth
        border.color: Theme.border
        Flickable {
            id: licenseView
            anchors.fill: parent
            anchors.margins: Theme.spaceLg
            clip: true
            contentHeight: licenseText.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            DgText {
                id: licenseText
                objectName: "aboutLicenseText"
                width: licenseView.width
                text: AppInfo.licenseText
                role: "small"
                secondary: true
                wrapMode: Text.WordWrap
                elide: Text.ElideNone
            }
        }
    }

    buttons: [
        DgButton { text: "Copy version details"; variant: "ghost"; onClicked: AppInfo.copy(AppInfo.details) },
        DgButton { text: "Close"; hint: "Esc"; variant: "primary"; onClicked: dialog.close() }
    ]
}
