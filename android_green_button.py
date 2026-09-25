from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Button:
    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


def run_adb(adb: str, serial: str | None, *arguments: str, capture_output: bool = False) -> subprocess.CompletedProcess[bytes]:
    device_arguments = ("-s", serial) if serial else ()
    try:
        return subprocess.run(
            [adb, *device_arguments, *arguments],
            check=True,
            capture_output=capture_output,
            timeout=10,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"Не удалось найти adb: {adb}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Команда adb не завершилась вовремя") from error
    except subprocess.CalledProcessError as error:
        details = error.stderr.decode(errors="replace").strip() if error.stderr else ""
        raise RuntimeError(details or "Команда adb завершилась с ошибкой") from error


def connected_devices(adb: str) -> list[str]:
    result = run_adb(adb, None, "devices", capture_output=True)
    return [
        line.split()[0]
        for line in result.stdout.decode(errors="replace").splitlines()[1:]
        if len(line.split()) >= 2 and line.split()[1] == "device"
    ]


def select_device(adb: str, serial: str | None) -> str:
    devices = connected_devices(adb)
    if serial:
        if serial not in devices:
            raise RuntimeError(f"Устройство {serial} не подключено или не авторизовано")
        return serial
    if not devices:
        raise RuntimeError("Не найдено подключённое и авторизованное устройство. Проверьте вывод команды adb devices")
    if len(devices) > 1:
        raise RuntimeError("Подключено несколько устройств. Укажите нужное через --serial")
    return devices[0]


def launch_application(adb: str, serial: str, package: str) -> None:
    run_adb(adb, serial, "shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1", capture_output=True)


def verify_package(adb: str, serial: str, package: str) -> None:
    result = run_adb(adb, serial, "shell", "pm", "path", package, capture_output=True)
    if not result.stdout.strip():
        raise RuntimeError(f"Пакет {package} не установлен на устройстве {serial}")


def take_screenshot(adb: str, serial: str) -> np.ndarray:
    result = run_adb(adb, serial, "exec-out", "screencap", "-p", capture_output=True)
    png_signature = b"\x89PNG\r\n\x1a\n"
    offset = result.stdout.find(png_signature)
    data = result.stdout[offset:] if offset >= 0 else result.stdout
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        normalized_data = re.sub(rb"(?<!\r)\r\n", b"\n", data).replace(b"\r\r\n", b"\r\n")
        image = cv2.imdecode(np.frombuffer(normalized_data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        preview = result.stdout[:80].decode(errors="replace").replace("\n", " ")
        raise RuntimeError(
            f"adb вернул некорректный снимок экрана: {len(result.stdout)} байт, начало ответа: {preview!r}"
        )
    return image


def find_green_button(image: np.ndarray) -> Button | None:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array((35, 80, 70)), np.array((95, 255, 255)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum_area = max(800, image.shape[0] * image.shape[1] * 0.001)
    candidates: list[Button] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        rectangle_area = width * height
        if area < minimum_area or width < 30 or height < 20:
            continue
        if rectangle_area == 0:
            continue
        ratio = width / height
        solidity = area / rectangle_area
        if not 0.5 <= ratio <= 12 or solidity < 0.7:
            continue
        score = area * solidity
        candidates.append(Button(x, y, width, height, score))

    return max(candidates, key=lambda button: button.score, default=None)


def tap(adb: str, serial: str, button: Button) -> None:
    x, y = button.center
    run_adb(adb, serial, "shell", "input", "tap", str(x), str(y), capture_output=True)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Находит и нажимает зелёную кнопку в Android-приложении через adb.")
    parser.add_argument("package", help="Имя пакета Android-приложения, например com.example.app")
    parser.add_argument("--adb", default="adb", help="Путь к исполняемому файлу adb")
    parser.add_argument("--serial", help="Серийный номер устройства из вывода adb devices")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        serial = select_device(arguments.adb, arguments.serial)
        verify_package(arguments.adb, serial, arguments.package)
        launch_application(arguments.adb, serial, arguments.package)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            button = find_green_button(take_screenshot(arguments.adb, serial))
            if button is not None:
                tap(arguments.adb, serial, button)
                print(f"Зелёная кнопка нажата: {button.center[0]}, {button.center[1]}")
                return 0
            time.sleep(0.25)
    except RuntimeError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Операция отменена", file=sys.stderr)
        return 130

    print("Зелёная кнопка не найдена за 10 секунд")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
