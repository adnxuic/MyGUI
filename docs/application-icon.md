# Application Icon

MyGUI uses `pictures/icons/app_icon.ico` for the native main-window icon,
Windows taskbar icon, and the default icon inherited by application windows.
Existing dialogs that explicitly select a feature-specific icon keep their
own icon.

## Configuration

`main.WINDOWS_APP_USER_MODEL_ID` is the stable `MyGUI.Desktop` identity used
to keep a source launch from being grouped under the Python interpreter.
`main.configure_windows_taskbar_identity()` assigns that identity through the
Windows Shell before `QApplication` is created. It takes no parameters and
returns whether the Windows identity was successfully applied; unsupported
platforms leave startup unchanged.

`main.APP_ICON_PATH` is the absolute `Path` returned by the package resource
locator for the icon asset. Resource
loading therefore follows the application's existing requirement that
`main.py` is launched from the repository root.

`main.configure_application_icon(application)` accepts the active
`QApplication`, assigns a `QIcon` loaded from `APP_ICON_PATH`, and returns that
same `QIcon`. `MainWindow` also assigns the icon explicitly so directly
constructed main windows use the application branding outside the normal
startup path.
