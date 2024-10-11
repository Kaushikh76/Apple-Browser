import sys
import os
import io
from dotenv import load_dotenv
from PyQt5.QtCore import QUrl, Qt, QTimer, QMetaObject, Q_ARG
from PyQt5.QtWidgets import (QApplication, QMainWindow, QToolBar, QLineEdit, QPushButton, 
                             QVBoxLayout, QHBoxLayout, QWidget, QTextEdit, QLabel, QTabWidget)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtGui import QIcon
from openai import OpenAI
from elevenlabs import ElevenLabs, VoiceSettings
from pydub import AudioSegment
from pydub.playback import play
import speech_recognition as sr
import threading

load_dotenv()

class AIBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-Powered Python Browser with Voice Assistant")
        self.setGeometry(100, 100, 1200, 800)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)

        browser_widget = QWidget()
        browser_layout = QVBoxLayout()
        browser_widget.setLayout(browser_layout)

        nav_bar = QToolBar()

        back_btn = QPushButton()
        back_btn.setIcon(QIcon.fromTheme("go-previous"))
        back_btn.clicked.connect(self.go_back)
        nav_bar.addWidget(back_btn)

        forward_btn = QPushButton()
        forward_btn.setIcon(QIcon.fromTheme("go-next"))
        forward_btn.clicked.connect(self.go_forward)
        nav_bar.addWidget(forward_btn)

        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self.reload_page)
        nav_bar.addWidget(reload_btn)

        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        nav_bar.addWidget(self.url_bar)

        self.ai_button = QPushButton("AI Analysis")
        self.ai_button.clicked.connect(self.toggle_ai_widget)
        nav_bar.addWidget(self.ai_button)

        browser_layout.addWidget(nav_bar)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBarDoubleClicked.connect(self.tab_open_doubleclick)
        self.tabs.currentChanged.connect(self.current_tab_changed)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)

        self.add_new_tab(QUrl('https://www.google.com'), 'Homepage')

        browser_layout.addWidget(self.tabs)

        main_layout.addWidget(browser_widget, 2)

        self.ai_widget = QWidget()
        self.ai_widget.setVisible(False)
        ai_layout = QVBoxLayout()
        self.ai_widget.setLayout(ai_layout)

        self.question_input = QLineEdit()
        self.question_input.setPlaceholderText("Ask a question about the current page")
        ai_layout.addWidget(self.question_input)

        analyze_button = QPushButton("Analyze Page")
        analyze_button.clicked.connect(self.analyze_page)
        ai_layout.addWidget(analyze_button)

        self.answer_display = QTextEdit()
        self.answer_display.setReadOnly(True)
        ai_layout.addWidget(self.answer_display)

        speak_button = QPushButton("Speak Answer")
        speak_button.clicked.connect(self.speak_answer)
        ai_layout.addWidget(speak_button)

        self.status_label = QLabel("AI is ready")
        ai_layout.addWidget(self.status_label)

        main_layout.addWidget(self.ai_widget, 1)

        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")
        self.client = OpenAI(api_key=openai_api_key)

        eleven_api_key = os.getenv("ELEVEN_API_KEY")
        if not eleven_api_key:
            raise ValueError("ELEVEN_API_KEY not found in .env file")
        self.eleven_client = ElevenLabs(api_key=eleven_api_key)

        self.recognizer = sr.Recognizer()
        self.is_listening = False
        self.listen_thread = None

        self.start_listening()

    def add_new_tab(self, qurl=None, label="Blank"):
        if qurl is None:
            qurl = QUrl('https://www.google.com')

        browser = QWebEngineView()
        browser.setUrl(qurl)
        i = self.tabs.addTab(browser, label)

        self.tabs.setCurrentIndex(i)

        browser.urlChanged.connect(lambda qurl, browser=browser:
                                   self.update_urlbar(qurl, browser))
        browser.loadFinished.connect(lambda _, i=i, browser=browser:
                                     self.tabs.setTabText(i, browser.page().title()))

    def tab_open_doubleclick(self, i):
        if i == -1:  
            self.add_new_tab()

    def current_tab_changed(self, i):
        qurl = self.tabs.currentWidget().url()
        self.update_urlbar(qurl, self.tabs.currentWidget())
        self.update_title(self.tabs.currentWidget())

    def close_current_tab(self, i):
        if self.tabs.count() < 2:
            return
        self.tabs.removeTab(i)

    def update_title(self, browser):
        if browser != self.tabs.currentWidget():
            return
        title = self.tabs.currentWidget().page().title()
        self.setWindowTitle(f"{title} - AI-Powered Python Browser")

    def navigate_to_url(self):
        q = QUrl(self.url_bar.text())
        if q.scheme() == "":
            q.setScheme("http")
        self.tabs.currentWidget().setUrl(q)

    def update_urlbar(self, q, browser=None):
        if browser != self.tabs.currentWidget():
            return
        self.url_bar.setText(q.toString())
        self.url_bar.setCursorPosition(0)

    def go_back(self):
        self.tabs.currentWidget().back()

    def go_forward(self):
        self.tabs.currentWidget().forward()

    def reload_page(self):
        self.tabs.currentWidget().reload()

    def toggle_ai_widget(self):
        self.ai_widget.setVisible(not self.ai_widget.isVisible())

    def analyze_page(self):
        self.status_label.setText("AI is analyzing the page...")
        self.tabs.currentWidget().page().toHtml(self.process_page_content)

    def process_page_content(self, html_content):
        question = "You are an AI powered Broweser fot the blind people. Summarize the main content of this webpage."
        
        prompt = f"Based on the following webpage content from URL: {self.tabs.currentWidget().url().toString()}, please {question}\n\nWebpage content:\n{html_content[:4000]}"
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant that analyzes web page content."},
                    {"role": "user", "content": prompt}
                ]
            )
            answer = response.choices[0].message.content
            self.answer_display.setText(answer)
            self.status_label.setText("AI analysis complete")
            self.speak_text(answer)
        except Exception as e:
            error_message = f"Error: {str(e)}"
            self.answer_display.setText(error_message)
            self.status_label.setText("AI analysis failed")
            self.speak_text(error_message)

    def speak_text(self, text):
        try:
            audio_stream = self.eleven_client.text_to_speech.convert(
                voice_id="EXAVITQu4vr4xnSDxMaL",
                optimize_streaming_latency="0",
                output_format="mp3_44100_128",
                text=text,
                voice_settings=VoiceSettings(
                    stability=0.1,
                    similarity_boost=0.3,
                    style=0.2,
                ),
            )
            
            audio_bytes = b"".join(chunk for chunk in audio_stream)
            
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            play(audio_segment)

        except Exception as e:
            print(f"Error in text-to-speech: {str(e)}")

    def speak_answer(self):
        text = self.answer_display.toPlainText()
        if text:
            self.speak_text(text)

    def start_listening(self):
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self.listen_for_wake_word)
        self.listen_thread.start()

    def stop_listening(self):
        self.is_listening = False
        if self.listen_thread:
            self.listen_thread.join()

    def listen_for_wake_word(self):
        while self.is_listening:
            with sr.Microphone() as source:
                print("Listening for wake word...")
                audio = self.recognizer.listen(source)
                try:
                    text = self.recognizer.recognize_google(audio).lower()
                    if "hey apple" in text:
                        self.speak_text("Hello, how can I help you?")
                        self.process_voice_command()
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    print(f"Could not request results from Google Speech Recognition service; {e}")

    def process_voice_command(self):
        with sr.Microphone() as source:
            print("Listening for command...")
            audio = self.recognizer.listen(source)
            try:
                command = self.recognizer.recognize_google(audio).lower()
                print(f"Command received: {command}")
                
                if "analyze this page" in command:
                    self.speak_text("Analyzing the current page")
                    self.analyze_page()
                elif "go back" in command:
                    self.speak_text("Going back")
                    self.go_back()
                elif "go forward" in command:
                    self.speak_text("Going forward")
                    self.go_forward()
                elif "open" in command:
                    url = command.split("open")[-1].strip()
                    self.speak_text(f"Opening {url}")
                    self.open_url_voice(url)
                else:
                    self.speak_text("Processing your query")
                    response = self.client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": command}]
                    )
                    answer = response.choices[0].message.content
                    self.speak_text(answer)

            except sr.UnknownValueError:
                self.speak_text("Sorry, I didn't understand that. Can you please repeat?")
            except sr.RequestError as e:
                self.speak_text("Sorry, there was an error processing your request.")

    def open_url_voice(self, url):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://www." + url  
        try:
            self.tabs.currentWidget().setUrl(QUrl(url))
            self.speak_text(f"Opening {url}")
        except Exception as e:
            self.speak_text(f"Sorry, I couldn't open the URL. Error: {str(e)}")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    browser = AIBrowser()
    browser.show()
    sys.exit(app.exec_())
