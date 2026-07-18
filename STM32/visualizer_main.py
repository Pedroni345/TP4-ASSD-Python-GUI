"""
TP4-ASSD Power Analyzer Visualizer (STM32 Version)

Simple PyQt5 GUI that displays processed power measurements from STM32.
No DSP calculations - just visualization of results already computed on hardware.
"""

import sys
import time
from threading import Thread, Event
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QGroupBox, QTabWidget, QProgressBar
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt5.QtGui import QFont, QColor
import pyqtgraph as pg

from stm32_measurement_reader import STM32Reader, PowerMeasurement


class MeasurementSignals(QObject):
    """Signals for threading measurement updates"""
    new_measurement = pyqtSignal(PowerMeasurement)
    connection_status = pyqtSignal(bool)
    error_message = pyqtSignal(str)


class ReaderThread(Thread):
    """Background thread that reads measurements from STM32"""

    def __init__(self, reader: STM32Reader, signals: MeasurementSignals):
        super().__init__(daemon=True)
        self.reader = reader
        self.signals = signals
        self.running = True

    def run(self):
        """Thread main loop"""
        if not self.reader.connect():
            self.signals.connection_status.emit(False)
            self.signals.error_message.emit(f"Failed to connect to {self.reader.port}")
            return

        self.signals.connection_status.emit(True)

        while self.running:
            measurement = self.reader.read_frame()
            if measurement:
                self.signals.new_measurement.emit(measurement)
            else:
                time.sleep(0.01)  # Small delay to prevent CPU spinning

    def stop(self):
        """Stop the reader thread"""
        self.running = False


class LiveMeasurementPanel(QWidget):
    """Display panel for power measurements"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize UI components"""
        layout = QGridLayout()

        # Title
        title = QLabel("Power Measurement Results")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title, 0, 0, 1, 4)

        row = 1

        # Voltage section
        layout.addWidget(self._create_value_display("Voltage (RMS)", "voltage_rms", "V"), row, 0)
        layout.addWidget(self._create_value_display("Voltage THD", "voltage_thd", "%"), row, 1)
        row += 1

        # Current section
        layout.addWidget(self._create_value_display("Current (RMS)", "current_rms", "A"), row, 0)
        layout.addWidget(self._create_value_display("Current THD", "current_thd", "%"), row, 1)
        row += 1

        # Frequency and phase
        layout.addWidget(self._create_value_display("Frequency", "frequency", "Hz"), row, 0)
        layout.addWidget(self._create_value_display("Phase Angle", "phase_angle", "°"), row, 1)
        row += 1

        # Power section
        layout.addWidget(self._create_value_display("Active Power (Total)", "power_active", "W"), row, 0)
        layout.addWidget(self._create_value_display("Reactive Power (Total)", "power_reactive", "VAR"), row, 1)
        row += 1

        layout.addWidget(self._create_value_display("Apparent Power (Total)", "power_apparent", "VA"), row, 0)
        layout.addWidget(self._create_value_display("Power Factor (Total)", "power_factor", ""), row, 1)
        row += 1

        # Fundamental power
        layout.addWidget(self._create_value_display("Active Power (Fundamental)", "power_fund", "W"), row, 0)
        layout.addWidget(self._create_value_display("Displacement PF", "dpf", ""), row, 1)
        row += 1

        # Statistics
        layout.addWidget(self._create_value_display("Blocks Averaged", "blocks_count", ""), row, 0)
        layout.addWidget(self._create_value_display("Last Update", "last_update", ""), row, 1)
        layout.addWidget(self._create_value_display("PGA Gains (V / I)", "pga_gains", ""), row, 2)

        self.setLayout(layout)

    def _create_value_display(self, label: str, key: str, unit: str) -> QGroupBox:
        """Create a value display box"""
        group = QGroupBox(label)
        group.setMinimumHeight(80)

        layout = QVBoxLayout()

        # Value label
        value_label = QLabel("---")
        value_font = QFont()
        value_font.setPointSize(18)
        value_font.setBold(True)
        value_label.setFont(value_font)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setObjectName(f"{key}_value")

        # Unit label
        if unit:
            unit_label = QLabel(unit)
            unit_font = QFont()
            unit_font.setPointSize(10)
            unit_label.setFont(unit_font)
            unit_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(value_label, 2)
            layout.addWidget(unit_label, 1)
        else:
            layout.addWidget(value_label)

        group.setLayout(layout)
        return group

    def update_measurement(self, measurement: PowerMeasurement):
        """Update all display values"""
        self._set_value("voltage_rms", f"{measurement.vrms:.2f}")
        self._set_value("voltage_thd", f"{measurement.thd_v:.2f}")
        self._set_value("current_rms", f"{measurement.irms:.3f}")
        self._set_value("current_thd", f"{measurement.thd_i:.2f}")
        self._set_value("frequency", f"{measurement.frequency:.2f}")
        self._set_value("phase_angle", f"{measurement.phi_deg:+.1f}")
        self._set_value("power_active", f"{measurement.p_total:.1f}")
        self._set_value("power_reactive", f"{measurement.q_total:+.1f}")
        self._set_value("power_apparent", f"{measurement.s_total:.1f}")
        self._set_value("power_factor", f"{measurement.tpf:.3f}")
        self._set_value("power_fund", f"{measurement.p_fund:.1f}")
        self._set_value("dpf", f"{measurement.dpf:.3f}")
        self._set_value("blocks_count", f"{measurement.n_blocks}")
        self._set_value("last_update", time.strftime("%H:%M:%S"))
        self._set_value("pga_gains", f"{measurement.v_gain}x / {measurement.i_gain}x")

    def _set_value(self, key: str, value: str):
        """Set a value label"""
        label = self.findChild(QLabel, f"{key}_value")
        if label:
            label.setText(value)


class HarmonicsPlot(QWidget):
    """Display harmonic magnitudes as bar charts"""

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """Initialize plot"""
        layout = QVBoxLayout()

        # Create pyqtgraph plots
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('bottom', 'Harmonic Order')
        self.plot_widget.setLabel('left', 'Magnitude (normalized)')
        self.plot_widget.setTitle('Voltage & Current Harmonics')
        self.plot_widget.setYRange(0, 1.0)
        self.plot_widget.showGrid(True, True, alpha=0.3)

        # Bar plot items
        self.v_bars = pg.BarGraphItem(x=range(1, 24), height=[0]*23, width=0.8, brush='b')
        self.i_bars = pg.BarGraphItem(x=[x+0.4 for x in range(1, 24)], height=[0]*23, width=0.8, brush='r')

        self.plot_widget.addItem(self.v_bars)
        self.plot_widget.addItem(self.i_bars)

        # Legend
        self.plot_widget.addLegend()
        self.v_bars.setOpts(name='Voltage')
        self.i_bars.setOpts(name='Current')

        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def update_harmonics(self, v_harmonics: list, i_harmonics: list):
        """Update harmonic display"""
        self.v_bars.setOpts(height=v_harmonics[:23])
        self.i_bars.setOpts(height=i_harmonics[:23])


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TP4-ASSD Power Analyzer - STM32 Edition")
        self.setGeometry(50, 50, 1600, 900)

        # Serial port settings
        self.port = '/dev/ttyUSB0'
        self.baudrate = 115200

        # Signals
        self.signals = MeasurementSignals()
        self.signals.new_measurement.connect(self.on_new_measurement)
        self.signals.connection_status.connect(self.on_connection_status)
        self.signals.error_message.connect(self.on_error)

        # Reader
        self.reader = None
        self.reader_thread = None

        # UI
        self.init_ui()
        self.show()

    def init_ui(self):
        """Initialize main UI"""
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Control bar
        control_layout = QHBoxLayout()

        # Port selection
        port_label = QLabel("Serial Port:")
        self.port_combo = QComboBox()
        self.port_combo.addItems(['/dev/ttyUSB0', '/dev/ttyUSB1', 'COM3', 'COM4', 'COM5'])
        self.port_combo.setCurrentText(self.port)
        self.port_combo.currentTextChanged.connect(self.on_port_changed)
        control_layout.addWidget(port_label)
        control_layout.addWidget(self.port_combo)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        control_layout.addWidget(self.connect_btn)

        # Status label
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        control_layout.addWidget(self.status_label)

        # PGA281 gain selection (voltage & current differential gain stages)
        gain_group = QGroupBox("PGA Gain")
        gain_layout = QHBoxLayout()

        gain_layout.addWidget(QLabel("Voltage:"))
        self.v_gain_combo = QComboBox()
        self.v_gain_combo.addItems([str(g) for g in STM32Reader.PGA_GAINS])
        self.v_gain_combo.setCurrentText("4")   # firmware default
        gain_layout.addWidget(self.v_gain_combo)

        gain_layout.addWidget(QLabel("Current:"))
        self.i_gain_combo = QComboBox()
        self.i_gain_combo.addItems([str(g) for g in STM32Reader.PGA_GAINS])
        self.i_gain_combo.setCurrentText("16")  # firmware default
        gain_layout.addWidget(self.i_gain_combo)

        self.apply_gain_btn = QPushButton("Apply")
        self.apply_gain_btn.clicked.connect(self.apply_pga_gains)
        self.apply_gain_btn.setEnabled(False)   # needs connection
        gain_layout.addWidget(self.apply_gain_btn)

        gain_group.setLayout(gain_layout)
        control_layout.addWidget(gain_group)

        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # Tabs for different views
        tabs = QTabWidget()

        # Tab 1: Live Measurements
        self.measurements_panel = LiveMeasurementPanel()
        tabs.addTab(self.measurements_panel, "Live Measurements")

        # Tab 2: Harmonics
        self.harmonics_plot = HarmonicsPlot()
        tabs.addTab(self.harmonics_plot, "Harmonics")

        # Tab 3: Info
        info_widget = self._create_info_tab()
        tabs.addTab(info_widget, "Information")

        main_layout.addWidget(tabs)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def _create_info_tab(self) -> QWidget:
        """Create information tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        info_text = QLabel(
            "<b>TP4-ASSD Power Analyzer - STM32 DSP Edition</b><br><br>"
            "<b>Signal Processing Pipeline:</b><br>"
            "1. High-Pass Filter (DC Removal, 1 Hz cutoff)<br>"
            "2. Zero-Crossing Detection (10-cycle blocks)<br>"
            "3. Goertzel Algorithm with Hann Window (Harmonics)<br>"
            "4. Power Calculations (Active, Reactive, Apparent)<br>"
            "5. THD Calculation (Voltage & Current)<br><br>"
            "<b>Interface:</b><br>"
            "UART @ 115200 baud (ST-Link VCP)<br>"
            "Binary Protocol: ~200 bytes per frame<br>"
            "Update Rate: ~1 frame per second<br><br>"
            "<b>Measurements:</b><br>"
            "• Voltage RMS & THD<br>"
            "• Current RMS & THD<br>"
            "• Active, Reactive, Apparent Power<br>"
            "• Power Factor (Total & Displacement)<br>"
            "• Phase Angle & Frequency<br>"
            "• Harmonic Magnitudes (1-23)<br>"
        )
        info_text.setWordWrap(True)
        info_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(info_text)
        layout.addStretch()

        widget.setLayout(layout)
        return widget

    def on_port_changed(self, port: str):
        """Handle port selection change"""
        self.port = port

    def toggle_connection(self):
        """Toggle STM32 connection"""
        if self.reader_thread is None or not self.reader_thread.is_alive():
            self.connect_reader()
        else:
            self.disconnect_reader()

    def connect_reader(self):
        """Start reader thread"""
        self.reader = STM32Reader(self.port, self.baudrate)
        self.reader_thread = ReaderThread(self.reader, self.signals)
        self.reader_thread.start()
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setStyleSheet("background-color: #ff9999;")

    def disconnect_reader(self):
        """Stop reader thread"""
        if self.reader_thread:
            self.reader_thread.stop()
            self.reader_thread.join(timeout=2.0)
            self.reader.disconnect()
            self.reader_thread = None
        self.connect_btn.setText("Connect")
        self.connect_btn.setStyleSheet("")
        self.apply_gain_btn.setEnabled(False)

    def apply_pga_gains(self):
        """Send selected PGA281 gains to the STM32"""
        v_gain = int(self.v_gain_combo.currentText())
        i_gain = int(self.i_gain_combo.currentText())

        if self.reader and self.reader.set_pga_gains(v_gain, i_gain):
            self.status_label.setText(f"Gains set: V={v_gain}x, I={i_gain}x ✓")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setText("Failed to send gains ✗")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")

    def on_new_measurement(self, measurement: PowerMeasurement):
        """Handle new measurement from STM32"""
        self.measurements_panel.update_measurement(measurement)
        self.harmonics_plot.update_harmonics(measurement.v_harmonics, measurement.i_harmonics)

    def on_connection_status(self, connected: bool):
        """Handle connection status change"""
        if connected:
            self.status_label.setText("Connected ✓")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.apply_gain_btn.setEnabled(True)
        else:
            self.status_label.setText("Connection Failed ✗")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.apply_gain_btn.setEnabled(False)

    def on_error(self, error_msg: str):
        """Handle error message"""
        print(f"Error: {error_msg}")
        self.status_label.setText(f"Error: {error_msg[:50]}")
        self.status_label.setStyleSheet("color: orange; font-weight: bold;")

    def closeEvent(self, event):
        """Clean up on window close"""
        self.disconnect_reader()
        event.accept()


def main():
    """Application entry point"""
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
