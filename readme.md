## Запуск
Для сборки проекта нужно склонировать проект и выполнить

```
docker compose build
```

Для запуска

```
docker compose up -d
```

В фале wb-example.js пример правил для обработки события постановки на охрану одной из областей


## Тестирование
Чтобы протестировать локально – нужно запустить MQTT сервер:

Создайте файл ./mosquitto/config/mosquitto.conf and add (only for debug)

```
listener 1880
allow_anonymous true
```


Запустите MQTT сервер

```
docker run -it -p 1880:1880 -p 9001:9001 -v "$PWD/mosquitto/config:/mosquitto/config"  eclipse-mosquitto
```

Тест

```
echo -e 'B2C20046"ADM-CID"0008L0#777[#777|3401 01 501][SУлица]_09:15:28,07-03-2025' | telnet localhost 8882
```

Или

```
echo -n 'B2C20046"ADM-CID"0008L0#777[#777|1401 02 501][SУлица]_09:15:28,07-03-2025' | nc 127.0.0.1 8882
```

Можно подписаться на топик для проверки значений через Python

```python
import json
import paho.mqtt.subscribe as subscribe


def print_msg(client, userdata, message):
    print("%s : %s" % (message.topic, message.payload))
    print(json.loads(message.payload))

subscribe.callback(print_msg, "#", hostname="localhost", port=1880)
```

Или консольную утилиту
```
mosquitto_sub -t "#" -v
```

Или использовать программу: https://mqtt-explorer.com/


Для проброса локального порта в целях отладки можно использовать
```
ssh -R 8882:localhost:8882 user@receiver_ip
```