import sys
import speedtest
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from datetime import datetime, timedelta
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import sqlite3
import time
import requests
import threading

plt.style.use('seaborn-v0_8-darkgrid')

class ImprovedSpeedTestWorker(QThread):
    """Улучшенный поток для теста скорости с обработкой таймаутов"""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(float, float, float, str, str)
    error = pyqtSignal(str)
    server_info = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.timeout = 30  # Таймаут в секундах
        self.servers = []  # Список серверов
        self.current_server = None
    
    def check_internet_connection(self):
        """Проверка наличия интернет-соединения"""
        try:
            # Быстрая проверка доступности интернета
            requests.get("http://1.1.1.1", timeout=5)
            requests.get("http://8.8.8.8", timeout=5)
            return True
        except:
            try:
                # Попытка через Google
                requests.get("http://www.google.com", timeout=5)
                return True
            except:
                return False
    
    def get_available_servers(self):
        """Получение списка доступных серверов"""
        try:
            self.progress.emit(5, "Поиск доступных серверов...")
            
            st = speedtest.Speedtest()
            st.get_servers()  # Получаем все серверы
            
            # Берем только ближайшие серверы
            servers = st.get_closest_servers(limit=10)
            
            # Форматируем информацию о серверах
            server_list = []
            for server in servers:
                info = {
                    'id': server['id'],
                    'name': server.get('name', 'Unknown'),
                    'country': server.get('country', 'Unknown'),
                    'sponsor': server.get('sponsor', 'Unknown'),
                    'd': server['d']
                }
                server_list.append(info)
                
                # Отправляем информацию о сервере в UI
                server_text = f"{info['sponsor']} - {info['name']}, {info['country']}"
                self.server_info.emit(server_text)
                time.sleep(0.1)  # Небольшая пауза для UI
            
            self.servers = server_list
            return True
            
        except Exception as e:
            self.error.emit(f"Ошибка при поиске серверов: {str(e)}")
            return False
    
    def test_single_server(self, server_info):
        """Тестирование на конкретном сервере"""
        try:
            st = speedtest.Speedtest()
            
            # Устанавливаем таймауты
            st.config['download_timeout'] = self.timeout
            st.config['upload_timeout'] = self.timeout
            
            # Используем конкретный сервер
            server = [server_info['id']]
            st.get_servers(servers=server)
            st.get_best_server()
            
            self.current_server = server_info
            
            # Тестируем с прогрессом
            self.progress.emit(30, "Тестирование скорости загрузки...")
            download = st.download() / 1_000_000
            
            self.progress.emit(60, "Тестирование скорости отдачи...")
            upload = st.upload() / 1_000_000
            
            self.progress.emit(90, "Измерение ping...")
            ping = st.results.ping
            
            return ping, download, upload
            
        except Exception as e:
            raise Exception(f"Сервер {server_info['sponsor']}: {str(e)}")
    
    def run(self):
        try:
            # Шаг 1: Проверка интернет-соединения
            self.progress.emit(0, "Проверка интернет-соединения...")
            
            if not self.check_internet_connection():
                self.error.emit("❌ Нет интернет-соединения. Проверьте подключение к сети.")
                return
            
            self.progress.emit(10, "✅ Интернет-соединение активно")
            time.sleep(0.5)
            
            # Шаг 2: Получение доступных серверов
            if not self.get_available_servers():
                return
            
            if not self.servers:
                self.error.emit("❌ Не найдено доступных серверов для тестирования")
                return
            
            self.progress.emit(20, f"✅ Найдено {len(self.servers)} серверов")
            time.sleep(0.5)
            
            # Шаг 3: Попытка тестирования на разных серверах
            last_error = ""
            
            for i, server in enumerate(self.servers[:3]):  # Пробуем только 3 лучших сервера
                try:
                    self.progress.emit(25, f"Попытка {i+1}/3: {server['sponsor']}...")
                    
                    ping, download, upload = self.test_single_server(server)
                    
                    # Успешный тест
                    self.progress.emit(100, "✅ Тест успешно завершен!")
                    self.finished.emit(
                        ping, download, upload,
                        server['sponsor'],
                        server['country']
                    )
                    return
                    
                except Exception as e:
                    last_error = str(e)
                    self.progress.emit(25 + i*10, f"⚠️  Сервер {server['sponsor']} не доступен, пробую другой...")
                    time.sleep(1)  # Пауза между попытками
            
            # Если все попытки не удались
            self.error.emit(f"❌ Все серверы недоступны. Последняя ошибка: {last_error}")
            
        except Exception as e:
            self.error.emit(f"❌ Неожиданная ошибка: {str(e)}")

class SpeedometerWidget(QWidget):
    """Виджет спидометра"""
    def __init__(self, title="Download", max_value=100, unit="Mbps"):
        super().__init__()
        self.title = title
        self.max_value = max_value
        self.unit = unit
        self.value = 0
        self.target_value = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.animate_value)
        self.animation_speed = 5  # Скорость анимации
        
    def set_value(self, value, animate=True):
        self.target_value = min(value, self.max_value)
        if not animate:
            self.value = self.target_value
            self.update()
        else:
            self.animation_timer.start(16)  # ~60 FPS
    
    def animate_value(self):
        diff = self.target_value - self.value
        if abs(diff) < 0.1:
            self.value = self.target_value
            self.animation_timer.stop()
        else:
            self.value += diff / self.animation_speed
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        size = min(self.width(), self.height()) - 20
        center = QPoint(self.width() // 2, self.height() // 2)
        radius = size // 2
        
        # Фон спидометра
        gradient = QRadialGradient(center, radius)
        gradient.setColorAt(0, QColor(240, 248, 255))
        gradient.setColorAt(1, QColor(200, 220, 240))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(100, 100, 150), 3))
        painter.drawEllipse(center, radius, radius)
        
        # Цветовые зоны
        painter.save()
        painter.translate(center)
        painter.rotate(-135)
        
        # Зеленая зона (0-70%)
        painter.setBrush(QBrush(QColor(0, 255, 0, 30)))
        painter.setPen(Qt.NoPen)
        painter.drawPie(-radius, -radius, radius*2, radius*2, 0, 189)  # 70% от 270°
        
        # Желтая зона (70-90%)
        painter.setBrush(QBrush(QColor(255, 255, 0, 30)))
        painter.drawPie(-radius, -radius, radius*2, radius*2, 189, 54)  # 20% от 270°
        
        # Красная зона (90-100%)
        painter.setBrush(QBrush(QColor(255, 0, 0, 30)))
        painter.drawPie(-radius, -radius, radius*2, radius*2, 243, 27)  # 10% от 270°
        
        painter.restore()
        
        # Деления и метки
        painter.save()
        painter.translate(center)
        painter.rotate(-135)
        
        for i in range(0, 11):
            angle = i * 27
            painter.rotate(27)
            
            if i % 2 == 0:
                painter.setPen(QPen(QColor(0, 0, 0), 3))
                painter.drawLine(radius - 20, 0, radius - 5, 0)
                
                painter.save()
                painter.rotate(-angle)
                value = i * (self.max_value / 10)
                painter.setFont(QFont("Arial", 9, QFont.Bold))
                painter.drawText(QRectF(radius - 50, -10, 40, 20), 
                                Qt.AlignRight | Qt.AlignVCenter, 
                                f"{int(value)}")
                painter.restore()
            else:
                painter.setPen(QPen(QColor(100, 100, 100), 2))
                painter.drawLine(radius - 15, 0, radius - 5, 0)
        
        painter.restore()
        
        # Стрелка
        angle = 135 + (self.value / self.max_value) * 270
        painter.save()
        painter.translate(center)
        painter.rotate(angle)
        
        # Цвет стрелки в зависимости от значения
        if self.value > self.max_value * 0.9:
            arrow_color = QColor(255, 0, 0)
        elif self.value > self.max_value * 0.7:
            arrow_color = QColor(255, 165, 0)
        else:
            arrow_color = QColor(0, 150, 0)
        
        painter.setBrush(QBrush(arrow_color))
        painter.setPen(QPen(arrow_color.darker(), 2))
        
        arrow = QPolygon([
            QPoint(0, 0),
            QPoint(-10, -5),
            QPoint(radius - 20, 0),
            QPoint(-10, 5)
        ])
        painter.drawPolygon(arrow)
        
        painter.restore()
        
        # Центральный круг
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        painter.setPen(QPen(Qt.black, 2))
        painter.drawEllipse(center, 10, 10)
        
        # Отображаем значение
        painter.setFont(QFont("Arial", 16, QFont.Bold))
        color = (QColor(255, 0, 0) if self.value > self.max_value * 0.9 
                else QColor(255, 165, 0) if self.value > self.max_value * 0.7 
                else QColor(0, 100, 0))
        painter.setPen(QPen(color))
        
        painter.drawText(QRectF(center.x() - 50, center.y() + 40, 100, 30),
                        Qt.AlignCenter,
                        f"{self.value:.1f} {self.unit}")
        
        # Заголовок
        painter.setFont(QFont("Arial", 12, QFont.Bold))
        painter.setPen(QPen(Qt.darkBlue))
        painter.drawText(QRectF(0, 10, self.width(), 30),
                        Qt.AlignCenter,
                        self.title)

class EnhancedMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = self.DatabaseManager()
        self.init_ui()
        self.test_in_progress = False
        self.load_data()
        
        # Автоматический тест при запуске (опционально)
        # QTimer.singleShot(1000, self.run_speed_test)
    
    class DatabaseManager:
        def __init__(self):
            self.db_file = "internet_speed_enhanced.db"
            self.init_db()
        
        def init_db(self):
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    ping REAL,
                    download REAL,
                    upload REAL,
                    server_name TEXT,
                    server_country TEXT,
                    success INTEGER DEFAULT 1
                )
            ''')
            conn.commit()
            conn.close()
        
        def save_test(self, ping, download, upload, server_name="", server_country="", success=True):
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO tests (timestamp, ping, download, upload, server_name, server_country, success)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (datetime.now(), ping, download, upload, server_name, server_country, 1 if success else 0))
            conn.commit()
            conn.close()
        
        def get_tests(self, days=None):
            conn = sqlite3.connect(self.db_file)
            query = "SELECT * FROM tests WHERE success = 1 ORDER BY timestamp DESC"
            if days:
                cutoff = datetime.now() - timedelta(days=days)
                query = f"SELECT * FROM tests WHERE success = 1 AND timestamp >= '{cutoff}' ORDER BY timestamp DESC"
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
    
    def init_ui(self):
        self.setWindowTitle("🌐 Internet Speed Monitor Pro v2.0")
        self.setGeometry(100, 100, 1400, 900)
        
        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Верхняя панель
        main_layout.addWidget(self.create_top_panel())
        
        # Центральная панель
        center_splitter = QSplitter(Qt.Horizontal)
        center_splitter.addWidget(self.create_left_panel())
        center_splitter.addWidget(self.create_right_panel())
        center_splitter.setSizes([400, 1000])
        main_layout.addWidget(center_splitter)
        
        # Нижняя панель
        main_layout.addWidget(self.create_bottom_panel())
        
        # Статус бар
        self.statusBar().showMessage("✅ Система готова к работе")
        
        self.apply_styles()
    
    def create_top_panel(self):
        panel = QWidget()
        layout = QHBoxLayout(panel)
        
        # Кнопка теста
        self.test_btn = QPushButton("🚀 Запустить тест скорости")
        self.test_btn.setIconSize(QSize(24, 24))
        self.test_btn.clicked.connect(self.run_speed_test)
        self.test_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a6fa5, stop:1 #6a8fc5);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a7fb5, stop:1 #7a9fd5);
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #888888;
            }
        """)
        layout.addWidget(self.test_btn)
        
        # Выбор сервера
        server_label = QLabel("Сервер:")
        layout.addWidget(server_label)
        
        self.server_combo = QComboBox()
        self.server_combo.addItem("Автоматический выбор (рекомендуется)")
        layout.addWidget(self.server_combo)
        
        # Выбор периода
        period_label = QLabel("Период:")
        layout.addWidget(period_label)
        
        self.period_combo = QComboBox()
        self.period_combo.addItems(["24 часа", "7 дней", "30 дней", "Все время"])
        self.period_combo.currentIndexChanged.connect(self.load_data)
        layout.addWidget(self.period_combo)
        
        layout.addStretch()
        
        # Индикатор сети
        self.network_status = QLabel("🌐 Сеть: Проверка...")
        layout.addWidget(self.network_status)
        
        # Проверка сети при запуске
        QTimer.singleShot(100, self.check_network_status)
        
        return panel
    
    def check_network_status(self):
        """Проверка статуса сети"""
        try:
            response = requests.get("http://1.1.1.1", timeout=3)
            if response.status_code < 400:
                self.network_status.setText("🌐 Сеть: Онлайн")
                self.network_status.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.network_status.setText("🌐 Сеть: Проблемы")
                self.network_status.setStyleSheet("color: orange; font-weight: bold;")
        except:
            self.network_status.setText("🌐 Сеть: Оффлайн")
            self.network_status.setStyleSheet("color: red; font-weight: bold;")
        
        # Периодическая проверка
        QTimer.singleShot(10000, self.check_network_status)
    
    def create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Группа спидометров
        group = QGroupBox("📊 ТЕКУЩИЕ ПОКАЗАТЕЛИ")
        group_layout = QGridLayout(group)
        
        self.download_gauge = SpeedometerWidget("СКОРОСТЬ ЗАГРУЗКИ", 200, "Мбит/с")
        self.upload_gauge = SpeedometerWidget("СКОРОСТЬ ОТДАЧИ", 100, "Мбит/с")
        self.ping_gauge = SpeedometerWidget("PING", 100, "мс")
        
        group_layout.addWidget(self.download_gauge, 0, 0)
        group_layout.addWidget(self.upload_gauge, 0, 1)
        group_layout.addWidget(self.ping_gauge, 1, 0, 1, 2)
        
        layout.addWidget(group)
        
        # Прогресс теста
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Готово: %p% - %v")
        layout.addWidget(self.progress_bar)
        
        # Статус теста
        self.test_status = QLabel("💤 Ожидание теста...")
        self.test_status.setAlignment(Qt.AlignCenter)
        self.test_status.setStyleSheet("""
            QLabel {
                padding: 10px;
                border-radius: 5px;
                background-color: #f0f0f0;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.test_status)
        
        # Информация о сервере
        self.server_info_label = QLabel("Сервер: не выбран")
        self.server_info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.server_info_label)
        
        return panel
    
    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Вкладки
        self.tab_widget = QTabWidget()
        
        # График скорости
        speed_tab = QWidget()
        self.speed_figure = Figure(figsize=(10, 6))
        self.speed_canvas = FigureCanvas(self.speed_figure)
        speed_layout = QVBoxLayout(speed_tab)
        speed_layout.addWidget(self.speed_canvas)
        
        # График ping
        ping_tab = QWidget()
        self.ping_figure = Figure(figsize=(10, 6))
        self.ping_canvas = FigureCanvas(self.ping_figure)
        ping_layout = QVBoxLayout(ping_tab)
        ping_layout.addWidget(self.ping_canvas)
        
        # Статистика
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        stats_layout.addWidget(self.stats_text)
        
        self.tab_widget.addTab(speed_tab, "📈 СКОРОСТЬ")
        self.tab_widget.addTab(ping_tab, "🎯 PING")
        self.tab_widget.addTab(stats_tab, "📊 СТАТИСТИКА")
        
        layout.addWidget(self.tab_widget)
        
        return panel
    
    def create_bottom_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # История тестов
        group = QGroupBox("📜 ИСТОРИЯ ТЕСТОВ")
        group_layout = QVBoxLayout(group)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            "Дата", "Время", "Ping", "Download", "Upload", "Сервер", "Страна"
        ])
        self.history_table.setAlternatingRowColors(True)
        
        group_layout.addWidget(self.history_table)
        layout.addWidget(group)
        
        return panel
    
    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f8ff;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 2px solid #4a6fa5;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #4a6fa5;
            }
            QTableWidget {
                background-color: white;
                alternate-background-color: #f9f9f9;
                gridline-color: #e0e0e0;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QHeaderView::section {
                background-color: #4a6fa5;
                color: white;
                padding: 8px;
                border: 1px solid #3a5a8c;
                font-weight: bold;
                font-size: 11px;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #e0e0e0;
                color: #666666;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #4a6fa5;
                border-bottom: 2px solid #4a6fa5;
            }
            QTabBar::tab:hover {
                background-color: #f0f0f0;
            }
            QProgressBar {
                border: 1px solid #cccccc;
                border-radius: 6px;
                background-color: white;
                text-align: center;
                font-weight: bold;
                height: 20px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a6fa5, stop:1 #6a8fc5);
                border-radius: 6px;
            }
        """)
    
    def run_speed_test(self):
        if self.test_in_progress:
            return
        
        self.test_in_progress = True
        self.test_btn.setEnabled(False)
        self.test_status.setText("🔄 Начинаю тестирование...")
        self.test_status.setStyleSheet("""
            QLabel {
                background-color: #fff8e1;
                color: #ff8f00;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        self.progress_bar.setValue(0)
        
        # Очищаем список серверов
        self.server_combo.clear()
        self.server_combo.addItem("Автоматический выбор (рекомендуется)")
        
        # Запускаем улучшенный тест
        self.worker = ImprovedSpeedTestWorker()
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.test_finished)
        self.worker.error.connect(self.test_error)
        self.worker.server_info.connect(self.add_server_to_list)
        self.worker.start()
    
    def add_server_to_list(self, server_info):
        """Добавление сервера в выпадающий список"""
        self.server_combo.addItem(server_info)
    
    def update_progress(self, value, message):
        self.progress_bar.setValue(value)
        self.test_status.setText(message)
        
        # Изменение цвета в зависимости от прогресса
        if value < 30:
            color = "#ff8f00"  # оранжевый
        elif value < 70:
            color = "#4caf50"  # зеленый
        else:
            color = "#2196f3"  # синий
        
        self.test_status.setStyleSheet(f"""
            QLabel {{
                background-color: #f5f5f5;
                color: {color};
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }}
        """)
    
    def test_finished(self, ping, download, upload, server_name, server_country):
        # Сохраняем результат
        self.db.save_test(ping, download, upload, server_name, server_country)
        
        # Обновляем спидометры с анимацией
        self.download_gauge.set_value(download)
        self.upload_gauge.set_value(upload)
        self.ping_gauge.set_value(ping)
        
        # Обновляем информацию о сервере
        self.server_info_label.setText(f"📡 Сервер: {server_name} ({server_country})")
        
        # Сбрасываем состояние
        self.test_in_progress = False
        self.test_btn.setEnabled(True)
        self.test_status.setText("✅ Тест успешно завершен!")
        self.test_status.setStyleSheet("""
            QLabel {
                background-color: #e8f5e9;
                color: #4caf50;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        self.progress_bar.setValue(100)
        
        # Обновляем данные
        self.load_data()
        
        # Показываем уведомление
        self.show_notification("Тест скорости", 
                             f"Download: {download:.1f} Мбит/с\n"
                             f"Upload: {upload:.1f} Мбит/с\n"
                             f"Ping: {ping:.1f} мс")
    
    def test_error(self, error_message):
        self.test_in_progress = False
        self.test_btn.setEnabled(True)
        self.test_status.setText(f"❌ {error_message}")
        self.test_status.setStyleSheet("""
            QLabel {
                background-color: #ffebee;
                color: #f44336;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
        """)
        
        # Показываем диалог с деталями ошибки
        self.show_error_dialog(error_message)
        
        # Сохраняем неудачный тест
        self.db.save_test(0, 0, 0, "", "", False)
    
    def show_error_dialog(self, error_message):
        dialog = QDialog(self)
        dialog.setWindowTitle("Ошибка тестирования")
        dialog.setModal(True)
        dialog.resize(500, 300)
        
        layout = QVBoxLayout(dialog)
        
        # Иконка ошибки
        icon_label = QLabel()
        icon_label.setPixmap(QIcon.fromTheme("dialog-error").pixmap(64, 64))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        # Сообщение об ошибке
        error_label = QLabel(f"<h3>Не удалось выполнить тест скорости</h3>")
        error_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(error_label)
        
        # Детали ошибки
        details = QTextEdit()
        details.setText(error_message)
        details.setReadOnly(True)
        details.setMaximumHeight(100)
        layout.addWidget(details)
        
        # Причины и решения
        solutions = QTextEdit()
        solutions.setHtml("""
        <h4>Возможные причины и решения:</h4>
        <ul>
        <li><b>Проверьте интернет-соединение</b> - убедитесь, что компьютер подключен к сети</li>
        <li><b>Отключите VPN и прокси</b> - они могут мешать тестированию</li>
        <li><b>Проверьте брандмауэр</b> - разрешите приложению доступ в интернет</li>
        <li><b>Попробуйте другой сервер</b> - некоторые серверы могут быть временно недоступны</li>
        <li><b>Подождите несколько минут</b> - проблема может быть на стороне сервиса</li>
        </ul>
        """)
        solutions.setReadOnly(True)
        layout.addWidget(solutions)
        
        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec_()
    
    def load_data(self):
        period_text = self.period_combo.currentText()
        days_map = {"24 часа": 1, "7 дней": 7, "30 дней": 30, "Все время": None}
        days = days_map.get(period_text)
        
        df = self.db.get_tests(days)
        
        if not df.empty:
            self.update_history_table(df)
            self.update_charts(df)
            self.update_statistics(df)
    
    def update_history_table(self, df):
        self.history_table.setRowCount(len(df))
        
        for i, row in df.iterrows():
            timestamp = pd.to_datetime(row['timestamp'])
            self.history_table.setItem(i, 0, QTableWidgetItem(timestamp.strftime("%d.%m.%Y")))
            self.history_table.setItem(i, 1, QTableWidgetItem(timestamp.strftime("%H:%M:%S")))
            self.history_table.setItem(i, 2, QTableWidgetItem(f"{row['ping']:.1f} мс"))
            self.history_table.setItem(i, 3, QTableWidgetItem(f"{row['download']:.1f} Мбит/с"))
            self.history_table.setItem(i, 4, QTableWidgetItem(f"{row['upload']:.1f} Мбит/с"))
            self.history_table.setItem(i, 5, QTableWidgetItem(row.get('server_name', 'Неизвестно')))
            self.history_table.setItem(i, 6, QTableWidgetItem(row.get('server_country', 'Неизвестно')))
            
            # Цветовая индикация для скорости
            download_item = self.history_table.item(i, 3)
            upload_item = self.history_table.item(i, 4)
            ping_item = self.history_table.item(i, 2)
            
            if row['download'] > 100:
                download_item.setBackground(QColor(220, 255, 220))
            elif row['download'] > 50:
                download_item.setBackground(QColor(255, 255, 200))
            else:
                download_item.setBackground(QColor(255, 220, 220))
            
            if row['upload'] > 50:
                upload_item.setBackground(QColor(220, 255, 220))
            elif row['upload'] > 20:
                upload_item.setBackground(QColor(255, 255, 200))
            else:
                upload_item.setBackground(QColor(255, 220, 220))
            
            if row['ping'] < 50:
                ping_item.setBackground(QColor(220, 255, 220))
            elif row['ping'] < 100:
                ping_item.setBackground(QColor(255, 255, 200))
            else:
                ping_item.setBackground(QColor(255, 220, 220))
        
        self.history_table.resizeColumnsToContents()
    
    def update_charts(self, df):
        # График скорости
        self.speed_figure.clear()
        ax1 = self.speed_figure.add_subplot(111)
        
        if len(df) > 1:
            df = df.sort_values('timestamp')
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            ax1.fill_between(df['timestamp'], 0, df['download'], 
                           alpha=0.3, color='green', label='Download')
            ax1.plot(df['timestamp'], df['download'], 'g-', 
                   linewidth=2, marker='o', markersize=4)
            
            ax1.fill_between(df['timestamp'], 0, df['upload'], 
                           alpha=0.3, color='blue', label='Upload')
            ax1.plot(df['timestamp'], df['upload'], 'b-', 
                   linewidth=2, marker='s', markersize=4)
            
            ax1.set_xlabel('Время', fontsize=10)
            ax1.set_ylabel('Скорость (Мбит/с)', fontsize=10)
            ax1.set_title('История скорости интернета', fontsize=12, fontweight='bold')
            ax1.legend(fontsize=9)
            ax1.grid(True, alpha=0.2)
            
            # Форматирование даты
            self.speed_figure.autofmt_xdate()
            
            # Добавляем средние линии
            avg_download = df['download'].mean()
            avg_upload = df['upload'].mean()
            ax1.axhline(y=avg_download, color='green', linestyle='--', alpha=0.5)
            ax1.axhline(y=avg_upload, color='blue', linestyle='--', alpha=0.5)
            
            ax1.text(df['timestamp'].iloc[-1], avg_download, 
                    f' Avg: {avg_download:.1f}', 
                    color='green', fontsize=8, va='bottom')
            ax1.text(df['timestamp'].iloc[-1], avg_upload, 
                    f' Avg: {avg_upload:.1f}', 
                    color='blue', fontsize=8, va='bottom')
        else:
            ax1.text(0.5, 0.5, 'Недостаточно данных для графика\nПроведите несколько тестов',
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax1.transAxes, fontsize=12, fontweight='bold')
        
        self.speed_canvas.draw()
        
        # График ping
        self.ping_figure.clear()
        ax2 = self.ping_figure.add_subplot(111)
        
        if len(df) > 1:
            colors = ['red' if x > 100 else 'orange' if x > 50 else 'green' 
                     for x in df['ping']]
            
            bars = ax2.bar(range(len(df)), df['ping'], color=colors, alpha=0.7)
            ax2.set_xlabel('Номер теста', fontsize=10)
            ax2.set_ylabel('Ping (мс)', fontsize=10)
            ax2.set_title('История ping', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.2, axis='y')
            
            # Добавляем значения на столбцы
            for i, bar in enumerate(bars):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.0f}', ha='center', va='bottom', fontsize=8)
        else:
            ax2.text(0.5, 0.5, 'Недостаточно данных для графика\nПроведите несколько тестов',
                    horizontalalignment='center', verticalalignment='center',
                    transform=ax2.transAxes, fontsize=12, fontweight='bold')
        
        self.ping_canvas.draw()
    
    def update_statistics(self, df):
        if df.empty:
            self.stats_text.setHtml("<h3>Нет данных для статистики</h3>")
            return
        
        stats = f"""
        <html>
        <head>
        <style>
            body {{ font-family: Arial; margin: 10px; }}
            h3 {{ color: #4a6fa5; }}
            .stat-row {{ margin: 5px 0; }}
            .good {{ color: green; font-weight: bold; }}
            .average {{ color: orange; font-weight: bold; }}
            .poor {{ color: red; font-weight: bold; }}
            .value {{ font-weight: bold; }}
        </style>
        </head>
        <body>
        
        <h3>📊 Статистика за {self.period_combo.currentText()}:</h3>
        
        <div class="stat-row">📅 <b>Период:</b> {df['timestamp'].min().split()[0]} - {df['timestamp'].max().split()[0]}</div>
        <div class="stat-row">🔢 <b>Количество тестов:</b> <span class="value">{len(df)}</span></div>
        
        <h4>📥 Скорость загрузки:</h4>
        <div class="stat-row">• Средняя: <span class="value">{df['download'].mean():.1f} Мбит/с</span></div>
        <div class="stat-row">• Максимальная: <span class="good">{df['download'].max():.1f} Мбит/с</span></div>
        <div class="stat-row">• Минимальная: <span class="poor">{df['download'].min():.1f} Мбит/с</span></div>
        <div class="stat-row">• Стабильность: 
            <span class="{'good' if df['download'].std() < 20 else 'average' if df['download'].std() < 50 else 'poor'}">
            {('Высокая' if df['download'].std() < 20 else 'Средняя' if df['download'].std() < 50 else 'Низкая')}
            </span>
        </div>
        
        <h4>📤 Скорость отдачи:</h4>
        <div class="stat-row">• Средняя: <span class="value">{df['upload'].mean():.1f} Мбит/с</span></div>
        <div class="stat-row">• Максимальная: <span class="good">{df['upload'].max():.1f} Мбит/с</span></div>
        <div class="stat-row">• Минимальная: <span class="poor">{df['upload'].min():.1f} Мбит/с</span></div>
        
        <h4>🎯 Ping:</h4>
        <div class="stat-row">• Средний: <span class="value">{df['ping'].mean():.1f} мс</span></div>
        <div class="stat-row">• Минимальный: <span class="good">{df['ping'].min():.1f} мс</span></div>
        <div class="stat-row">• Максимальный: <span class="poor">{df['ping'].max():.1f} мс</span></div>
        <div class="stat-row">• Качество соединения: 
            <span class="{'good' if df['ping'].mean() < 50 else 'average' if df['ping'].mean() < 100 else 'poor'}">
            {('Отличное' if df['ping'].mean() < 50 else 'Хорошее' if df['ping'].mean() < 100 else 'Плохое')}
            </span>
        </div>
        
        <h4>📈 Рекомендации:</h4>
        """
        
        # Добавляем рекомендации
        avg_download = df['download'].mean()
        avg_ping = df['ping'].mean()
        
        if avg_download < 10:
            stats += "<div class='stat-row poor'>⚠️ Скорость загрузки очень низкая. Рекомендуется проверить подключение к роутеру.</div>"
        elif avg_download < 50:
            stats += "<div class='stat-row average'>⚠️ Скорость загрузки средняя. Возможны проблемы при загрузке больших файлов.</div>"
        else:
            stats += "<div class='stat-row good'>✅ Скорость загрузки отличная!</div>"
        
        if avg_ping > 100:
            stats += "<div class='stat-row poor'>⚠️ Высокий ping. Возможны задержки в онлайн-играх и видеозвонках.</div>"
        elif avg_ping > 50:
            stats += "<div class='stat-row average'>⚠️ Ping средний. Для онлайн-игр рекомендуется оптимизировать соединение.</div>"
        else:
            stats += "<div class='stat-row good'>✅ Ping отличный! Идеально для онлайн-игр и видеозвонков.</div>"
        
        stats += "</body></html>"
        self.stats_text.setHtml(stats)
    
    def show_notification(self, title, message):
        """Показ красивого уведомления"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIconPixmap(QIcon.fromTheme("network-wireless").pixmap(64, 64))
        
        # Стилизация
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: white;
            }
            QMessageBox QLabel {
                font-size: 12px;
                font-family: Arial;
            }
        """)
        
        msg_box.exec_()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Устанавливаем иконку приложения
    app.setWindowIcon(QIcon.fromTheme("network-wireless"))
    
    window = EnhancedMainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
