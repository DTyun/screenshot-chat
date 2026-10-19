COLORS = dict(primary='#00C878', primary_hover='#00B46B', background='#FAFAFA', panel='#EFEFF1', rail='#E2E3E7', surface='#FAFAFA', text='#242424', muted='#92929C', border='#E2E2E6', selected='#E2E2E5', danger='#C53939', thumb='#B8B8BE')


WINDOW_CORNER_RADIUS = 10


def stylesheet():
    c = COLORS
    return f'''
    QWidget {{ font-family: "Microsoft YaHei UI"; font-size: 13px; color: {c['text']}; }}
    QMainWindow, QDialog, QWidget#root {{ background: {c['background']}; }}
    QLabel {{ background: transparent; }}
    QFrame#titleBar {{ background: {c['rail']}; }}
    QCheckBox {{ spacing: 8px; padding: 4px 0; }}
    QTextEdit {{ background: transparent; border: none; padding: 0; font-size: 14px; }}
    QPushButton#addChat {{ font-size: 22px; padding: 0; }}
    QLineEdit {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 9px; }}
    QLineEdit:focus {{ border: 1px solid {c['primary']}; }}
    QTabBar::tab {{ padding: 8px 16px; background: transparent; }}
    QTabBar::tab:selected {{ color: {c['primary_hover']}; border-bottom: 2px solid {c['primary']}; }}
    QPushButton#searchLink {{ color: #355BA6; }}
    QListWidget#chatList {{ background: {c['panel']}; }}
    QListWidget#chatList::item {{ padding: 4px; border-radius: 5px; }}
    QListWidget#chatList::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
    QFrame#rail {{ background: {c['rail']}; }}
    QFrame#sidebar {{ background: {c['panel']}; border-right: 1px solid {c['border']}; }}
    QFrame#conversation {{ background: {c['selected']}; border-radius: 5px; }}
    QFrame#header {{ border-bottom: 1px solid #F0F0F2; }}
    QFrame#composer {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
    QLabel#title {{ font-size: 16px; font-weight: 500; }}
    QLabel#status {{ color: {c['muted']}; font-size: 12px; padding: 4px; }}
    QPushButton {{ border: 1px solid transparent; background: transparent; padding: 7px 12px; border-radius: 4px; }}
    QPushButton:hover {{ background: {c['panel']}; }}
    QPushButton:pressed {{ background: {c['selected']}; }}
    QPushButton:focus {{ border: 1px solid {c['primary']}; }}
    QPushButton:disabled {{ color: #A0A0A0; background: {c['panel']}; }}
    QPushButton#primary {{ background: {c['primary']}; color: white; padding: 5px 18px; border-radius: 6px; }}
    QPushButton#primary:hover {{ background: {c['primary_hover']}; }}
    QPushButton#primary:disabled {{ background: {c['panel']}; color: #999999; }}
    QPushButton#danger {{ color: {c['danger']}; }}
    QPushButton#railButton {{ color: #686970; font-family: "Segoe UI Symbol"; font-size: 22px; padding: 6px; }}
    QPushButton#railButton:hover {{ background: #D3D4DA; }}
    QLabel#shortcutValue {{ color: #4D555D; font-size: 13px; font-weight: 600; }}
    QPushButton#editHotkey {{ background: #F8F8FA; color: #59616B; border: 1px solid #DCDDE2; border-radius: 6px; padding: 0 12px; }}
    QPushButton#editHotkey:hover {{ background: #E5E7EA; border-color: #CDD0D5; }}
    QPushButton#editHotkey:pressed {{ background: #DDE1E4; }}
    QPushButton#editHotkey:focus {{ border-color: {c['primary']}; }}
    QPushButton#selectedRail {{ color: {c['primary']}; background: transparent; font-family: "Segoe UI Symbol"; font-size: 24px; padding: 6px; }}
    QListWidget {{ background: {c['background']}; border: none; outline: none; }}
    QListWidget::item:selected {{ background: transparent; }}
    QScrollBar:vertical {{ width: 10px; background: {c['background']}; margin: 1px; }}
    QScrollBar::handle:vertical {{ background: {c['thumb']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: #929292; }}
    QScrollBar::handle:vertical:pressed {{ background: #737373; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QMenu {{ background: white; border: 1px solid {c['border']}; padding: 5px; }}
    QMenu::item {{ padding: 8px 28px; }}
    QMenu::item:selected {{ background: {c['panel']}; }}
    QKeySequenceEdit {{ background: white; border: 1px solid {c['border']}; border-radius: 4px; padding: 10px; }}
    '''
