import sys
from PyQt5.QtWidgets import QApplication
from client.ui.login_window import LoginWindow
from client.ui.register_window import RegisterWindow
from client.ui.main_window import MainWindow
from client.core.api_client import APIClient

def main():
    app = QApplication(sys.argv)
    
    api_client = APIClient()
    
    login_window = LoginWindow(api_client)
    register_window = RegisterWindow(api_client)
    
    # We need to keep a reference to the main window, otherwise it will be garbage collected
    main_window = None

    def show_main_window(user_data):
        nonlocal main_window
        main_window = MainWindow(api_client, user_data)
        main_window.show()
        login_window.close()
        register_window.close()

    def show_register():
        login_window.hide()
        register_window.show()

    def show_login():
        register_window.hide()
        login_window.show()

    login_window.login_success.connect(show_main_window)
    login_window.switch_to_register.connect(show_register)
    register_window.switch_to_login.connect(show_login)
    
    login_window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
