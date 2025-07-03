import asyncio
import json
import logging
import os
import re

import paho.mqtt.publish as publish

from dataclasses import dataclass

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
)

logger = logging.getLogger(__name__)

SERVICE_TEST_REPORT_CODE = 602

with open("event_codes.json", "r", encoding="utf-8") as f:
    event_codes_json = json.load(f)
    EVENT_CODES = {entry["cid_code"]: entry for entry in event_codes_json}

if allowed_clients := os.environ.get('ALLOWED_CLIENTS'):
    ALLOWED_CLIENTS = allowed_clients.split(',')
else:
    ALLOWED_CLIENTS = []

# Функция расчета CRC-16/ARC
def calculate_crc16_for_string(input_str: str) -> str:
    crc = 0x0000
    poly = 0xA001
    for byte in input_str.encode('utf-8'):
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ poly
            else:
                crc >>= 1
    return crc & 0xFFFF


class InvalidEventException(Exception):
    pass


@dataclass
class CIAData:
    panel_number: str
    event_qualifier: str
    cid_code: str
    event_code: str
    description: str
    group_or_partition_number: str
    zone_number_or_user_number: str
    meta: str
    

@dataclass
class Event:
    """
    Data example: B2C20046"ADM-CID"0008L0#777[#777|1401 02 501][SУлица]_09:15:28,07-03-2025
    """

    raw: str
    checksum: str
    lengthHex: str
    protocol: str
    line: str

    prefix: int
    panel_number: int
    data: CIAData
    time: int
    date: int

    @classmethod
    def from_data(cls, data: str) -> dict:

        pattern = r'^([A-F0-9]{4})([A-F0-9]{4})"(ADM-CID|NULL)"(\d+)L(\d+)#(\d+)\[(.*?)\]_([\d:]+),([\d-]+)$'
        match = re.match(pattern, data)

        if not match:
            raise InvalidEventException("Invalid message")

        return cls(
            raw=data,
            checksum=match.group(1),
            lengthHex=match.group(2),
            protocol=match.group(3),
            line=match.group(4),
            prefix=match.group(5),
            panel_number=match.group(6),
            data=Event.parse_adc_cid(match.group(7)),
            time=match.group(8),
            date=match.group(9),
        )
    
    @classmethod
    def parse_adc_cid(cls, data: str) -> dict:
        message_blocks = data.split('|')

        # starts with a #ACCT, so we drop the pound
        account_number = int(message_blocks[0][1:])

        contact_id = message_blocks[1].split(' ')

        cid_code = contact_id[0]

        if item := EVENT_CODES.get(cid_code):
            description = item["description"] 
        else:
            description = None

        # 1 = New Event or Opening,
        # 3 = New Restore or Closing,
        # 6 = Previously reported condition still present (Status report)
        event_qualifier = int(cid_code[0])

        # 3 decimal(!) digits XYZ (e.g. 602)
        event_code = int(cid_code[1:])

        # 2 decimal(!) digits GG, 00 if no info (e.g. 01)
        group_or_partition_number = contact_id[1]

        tail = contact_id[2].split('][')
        # 3 decimal(!) digits CCC, 000 if no info (e.g. 001)
        zone_number_or_user_number = tail[0]

        meta = tail[1:]

        return CIAData(
            panel_number=account_number,
            event_qualifier=event_qualifier,
            cid_code=cid_code,
            event_code=event_code,
            description=description,
            group_or_partition_number=group_or_partition_number,
            zone_number_or_user_number=zone_number_or_user_number,
            meta=meta
        )

    def generate_ack_message(self) -> str:
        response_body = f'"ACK"{self.line}L{self.prefix}#{self.panel_number}[]_{self.time},{self.date}'
        crc = calculate_crc16_for_string(response_body)
        length_hex = f"{len(response_body):04X}"
        crc_hex = f"{crc:04X}"
        return f"\n{crc_hex}{length_hex}{response_body}\r"

    def is_test(self):
        return self.data.event_code == SERVICE_TEST_REPORT_CODE

    def to_mqtt(self):
        return json.dumps({
            'panel_number': self.panel_number,
            'event_qualifier': self.data.event_qualifier,
            'event_code': self.data.event_code,
            'group_or_partition_number': self.data.group_or_partition_number,
            'zone_number_or_user_number': self.data.zone_number_or_user_number,
            'description': self.data.description
        })


class ADMCIDServer:
    def __init__(self, host, port, callback=None):
        self.host = host
        self.port = port
        self.callback = callback

    async def handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logger.info(f'Connection from {addr}')
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                try:
                    decoded_data = data.decode().strip()
                except UnicodeDecodeError as e:
                    logger.error(f"Decode error: {e}")
                    break
                try:
                    event = Event.from_data(decoded_data)
                except InvalidEventException as e:
                    logger.error(f"Invalid event: {decoded_data} Error: {e}")
                    break
                else:
                    self.callback(event)

                ack = event.generate_ack_message()
                writer.write(ack.encode())
                await writer.drain()  # Ensure the data is sent
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f'Connection closed for {addr}')

    async def run_server(self):
        server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port
        )
        addr = server.sockets[0].getsockname()
        logger.info(f'Serving on {addr}')

        async with server:
            await server.serve_forever()

    def start(self):
        try:
            asyncio.run(self.run_server())
        except KeyboardInterrupt:
            logger.info("Server stopped.")


# Define the callback function to process received alarm data
def process_alarm(event):
    """
    Check if the client code is in the allowed list
    and the event code is not '602' (suppress polling messages)
    """
    if event.panel_number in ALLOWED_CLIENTS:
        if not event.is_test():
            logger.info(f"Event: {event.raw} Description: {event.data.description}")
            try:
                publish.single(
                    topic=f"/devices/ax-pro/controls/Log/{event.data.group_or_partition_number}/{event.data.zone_number_or_user_number}",
                    payload=event.to_mqtt(),
                    client_id=event.panel_number,
                    hostname=os.environ.get('MQTT_HOSTNAME', 'localhost'),
                    port=int(os.environ.get('MQTT_PORT', 1880)),
                )
            except ConnectionRefusedError as e:
                logger.error(f"MQTT server is not available: {e}")
            except TimeoutError as e:
                logger.error(f"MQTT server is not available: {e}")
        else:
            logger.info("Test ok")
    else:
        logger.error(f"Client code {event.panel_number} is not allowed")


server = ADMCIDServer(
    callback=process_alarm,
    host=os.environ.get('SERVER_HOST', '0.0.0.0'),
    port=int(os.environ.get('SERVER_PORT', 8882))
)

# Start the server to listen for incoming alarm messages
server.start()
