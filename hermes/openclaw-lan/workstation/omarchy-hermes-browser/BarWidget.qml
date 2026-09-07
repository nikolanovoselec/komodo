import QtQuick
import qs.Ui

BarWidget {
  id: root
  moduleName: "nikolanovoselec.hermes-browser"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "⚕"
    horizontalMargin: 7.5
    tooltipText: "Hermes Browser"
    onPressed: function(button) {
      if (!root.bar) return
      if (button === Qt.RightButton)
        root.bar.run("xdg-open 'http://127.0.0.1:6080/'")
      else
        root.bar.run("xdg-open 'https://hermes.novoselec.ch/browser/'")
    }
  }
}
