BG = "#FAF3E3"
PAGE = "#FFFCF5"
LINE = "#E9DCC3"
INK = "#3A2E22"
MUTED = "#75634D"
STAR = "#C9862A"
OK = "#2FB862"
NO = "#B8A990"
DIM = "#B8A990"
FONT = "Microsoft YaHei"
FONT_STEM = "Noto Sans SC DemiLight"
SERIF = FONT
SANS = FONT
QSS = f"""
QWidget {{
  background: {BG};
  color: {INK};
  font-family: "{FONT}";
}}
QLabel {{ background: transparent; }}
QLabel#brand {{ font-size: 18px; font-weight: normal; }}
QLabel#brandBig {{ font-size: 33px; font-weight: normal; }}
QLabel#lab {{ font-size: 24px; font-weight: bold; }}
QPushButton#ghost {{
  background: transparent;
  border: none;
  color: rgba(58,46,34,0.40);
  font-size: 15px;
  padding: 0 12px;
}}
QPushButton#ghost:hover {{ color: rgba(58,46,34,0.62); }}
QPushButton#who {{
  background: transparent;
  border: 2px solid {LINE};
  border-radius: 999px;
  padding: 2px 12px;
  font-size: 15px;
  font-weight: bold;
  color: {INK};
}}
QPushButton#who[on="true"] {{ background: {INK}; color: #FFFFFF; border-color: {INK}; }}
QPushButton#go {{
  background: {OK};
  border: none;
  border-radius: 999px;
  color: #FFFFFF;
  font-size: 56px;
}}
QPushButton#go:hover {{ background: #28A455; }}
QLineEdit#note {{
  background: #FFFDF7;
  border: 2px solid {LINE};
  border-radius: 14px;
  padding: 4px 14px;
  color: {INK};
  selection-background-color: #EAD9B8;
}}
QWidget#slot {{
  background: rgba(58,46,34,0.05);
  border-radius: 17px;
}}
QWidget#opt {{
  background: transparent;
  border: 2px solid transparent;
  border-radius: 17px;
}}
QWidget#opt[state="ok"] {{
  background: {PAGE};
  border: 2px solid rgba(47,184,98,0.72);
}}
QTextBrowser#stem {{ background: transparent; border: none; }}
"""
