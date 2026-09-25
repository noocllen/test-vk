# Android green button

Скрипт запускает Android-приложение через `adb`, в течение 10 секунд ищет на экране зелёную кнопку и нажимает её. Для поиска используется снимок экрана и обработка изображения OpenCV; UI-автоматизаторы не используются.

Требования: Python 3.12, Android Platform Tools (`adb`) в `PATH`, подключённое и авторизованное устройство.

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 .\android_green_button.py com.example.application
```

`com.example.application` в примерах замените на фактическое имя пакета тестируемого приложения. Его можно определить через `adb shell pm list packages` или получить у разработчиков приложения.

При нескольких подключённых устройствах укажите серийный номер из вывода `adb devices`:

```powershell
adb devices
py -3.12 .\android_green_button.py com.example.application --serial R58N123ABC
```

Если вывод `adb devices` не содержит строки со статусом `device`, включите отладку по USB на телефоне, подтвердите ключ RSA и переподключите устройство. При ошибке `device '(null)' not found` удалите некорректную переменную текущего сеанса PowerShell:

```powershell
Remove-Item Env:ANDROID_SERIAL -ErrorAction SilentlyContinue
```

Если `adb` не находится в `PATH`, передайте путь к нему:

```powershell
py -3.12 .\android_green_button.py com.example.application --adb C:\Android\platform-tools\adb.exe
```

Код завершения `0` означает успешное нажатие, `1` — зелёная кнопка не была найдена за 10 секунд, `2` — ошибка `adb` или получения снимка экрана.
