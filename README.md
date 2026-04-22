# WebRTC YOLO Camera

CPU-only сайт для real-time обработки камеры: браузер отправляет webcam stream на сервер через WebRTC, сервер прогоняет кадры через OpenCV + YOLOv8n, возвращает размеченное видео и JSON с detections через WebRTC DataChannel.

## Быстрый запуск

```bash
docker compose up --build
```

После запуска откройте:

```text
http://localhost:8000
```

Проверка API:

```bash
curl http://localhost:8000/health
```

## Настройки

Переменные окружения в `docker-compose.yml`:

- `MODEL_PATH` - путь к YOLO модели, по умолчанию `/app/yolov8n.pt`.
- `YOLO_CONF` - минимальная confidence, по умолчанию `0.35`.
- `YOLO_IMGSZ` - размер входа YOLO, по умолчанию `640`.
- `DETECT_EVERY_N` - запускать YOLO раз в N кадров. Для слабого CPU можно поставить `2` или `3`; рамки будут переиспользоваться между инференсами.
- `PRELOAD_MODEL` - загрузить модель при старте приложения. По умолчанию `false`, потому что модель уже скачивается на этапе Docker build.

## Серверный деплой

Базовый `docker-compose.yml` пробрасывает порт `8000:8000`, поэтому он удобен для Docker Desktop и простой локальной проверки.

На Linux VPS для WebRTC часто надежнее использовать host networking, чтобы aiortc отдавал браузеру ICE candidates, доступные снаружи контейнера:

```bash
docker compose -f docker-compose.linux-host.yml up --build
```

Для реального домена нужен HTTPS, иначе браузер не даст доступ к камере. Исключение только `localhost`.

Пример с Caddy на хосте:

```caddyfile
camera.example.com {
  reverse_proxy 127.0.0.1:8000
}
```

Откройте входящий TCP `80/443` для сайта. Для WebRTC также убедитесь, что UDP-трафик между браузером и сервером не заблокирован. Если сервер находится за сложным NAT или корпоративной сетью, понадобится TURN-сервер.

## Локальная разработка

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload
```

Unit-тесты:

```bash
.venv/bin/python -m pytest -q
```

## Что видно в интерфейсе

- обработанный сервером WebRTC stream с bbox/labels;
- live JSON detections в списке;
- FPS, время инференса и количество объектов.

## Производительность CPU

Если FPS низкий:

- уменьшите `YOLO_IMGSZ`, например до `416` или `320`;
- увеличьте `DETECT_EVERY_N` до `2` или `3`;
- поднимите `YOLO_CONF`, чтобы меньше объектов рисовалось и отправлялось.
