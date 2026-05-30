import asyncio
import sqlite3
import psycopg2
import struct
import time
import smtplib
import ssl

from datetime import datetime
from email.message import EmailMessage

from gpiozero import Button
from bleak import BleakClient
from pymodbus.client import ModbusSerialClient


# ===================================================
# CONFIG
# ===================================================

SLAVE_ID = 1

DEVICE_ADDRESS = "D5:CF:7B:74:6B:3B"
TEMP_UUID = "00040000-0001-11e1-ac36-0002a5d5c51b"

DB = "hvac_demo.db"

EMAIL = "pehuenyt@gmail.com"
PASSWORD = "piul ibrj wcnv cmow"
DESTINO = "pehuen88@gmail.com"

DOOR_GPIO = 17
WINDOW_GPIO = 18


# ===================================================
# REGISTROS TERMOSTATO
# ===================================================

AMBIENT_TEMP = 9
SETPOINT = 6
SETPOINT_EFFECTIVE = 8
MODE = 10
FAN = 12

ONOFF = 98


# ===================================================
# VARIABLES GLOBALES
# ===================================================

outdoor_temp = None

door_open = False
window_open = False

door_start = None
window_start = None

alert_sent = False
reduce_done = False
shutdown_done = False
last_ble_data = None

# ===================================================
# GPIO
# ===================================================

door = Button(DOOR_GPIO,pull_up=True)
window = Button(WINDOW_GPIO,pull_up=True)

def init_sensor_states():

    global door_open
    global window_open
    global door_start
    global window_start


    # -------- PUERTA --------

    if door.is_pressed:

        door_open = False
        door_start = None

        print(
            "[INIT] puerta cerrada"
        )

    else:

        door_open = True
        door_start = time.time()

        print(
            "[INIT] puerta abierta"
        )


    # -------- VENTANA --------

    if window.is_pressed:

        window_open = False
        window_start = None

        print(
            "[INIT] ventana cerrada"
        )

    else:

        window_open = True
        window_start = time.time()

        print(
            "[INIT] ventana abierta"
        )

def door_opened():

    global door_open,door_start

    door_open=True
    door_start=time.time()

    print("[INFO] puerta abierta")


def door_closed():

    global door_open,door_start

    door_open=False
    door_start=None

    print("[INFO] puerta cerrada")


door.when_released=door_opened
door.when_pressed=door_closed


def window_opened():

    global window_open,window_start

    window_open=True
    window_start=time.time()

    print("[INFO] ventana abierta")


def window_closed():

    global window_open,window_start

    window_open=False
    window_start=None

    print("[INFO] ventana cerrada")


window.when_released=window_opened
window.when_pressed=window_closed


# ===================================================
# MODBUS
# ===================================================

client = ModbusSerialClient(

    port="/dev/ttyUSB0",
    baudrate=9600,
    parity="N",
    stopbits=1,
    timeout=2

)


def parse_temp(v):

    if v>100:

        return v/10

    return v


def read_reg(reg):

    r=client.read_holding_registers(

        address=reg,
        count=1,
        device_id=SLAVE_ID

    )

    if r.isError():

        return 0


    return parse_temp(
        r.registers[0]
    )


# ===================================================
# BLE
# ===================================================

def temp_callback(sender,data):

    global outdoor_temp
    global last_ble_data
    
    temp_raw=struct.unpack(

        "<h",
        data[2:4]

    )[0]

    outdoor_temp=temp_raw/10
    last_ble_data = time.time()

# ===================================================
# EMAIL DETALLADO
# ===================================================

def send_email():

    ambient=read_reg(
        AMBIENT_TEMP
    )

    setpoint=read_reg(
        SETPOINT_EFFECTIVE
    )

    mode=read_reg(
        MODE
    )

    fan=read_reg(
        FAN
    )

    hvac=read_reg(
        ONOFF
    )


    door_time=0
    window_time=0


    if door_open:

        door_time=int(
            time.time()-door_start
        )


    if window_open:

        window_time=int(
            time.time()-window_start
        )


    modos={

        0:"Vent",
        1:"Frío",
        2:"Calor",
        3:"Auto"

    }


    fan_txt={

        0:"Auto",
        1:"Baja",
        2:"Media",
        3:"Alta"

    }


    asunto="⚠ ALERTA HVAC"



    cuerpo=f"""

Sistema optimización HVAC


Fecha:

{datetime.now()}



ESTADO DETECTADO

Puerta:

{"ABIERTA" if door_open else "CERRADA"}

Ventana:

{"ABIERTA" if window_open else "CERRADA"}



TIEMPO APERTURA

Puerta:

{door_time} segundos


Ventana:

{window_time} segundos



ESTADO HVAC

Temperatura ambiente:

{ambient} °C


Consigna:

{setpoint} °C


Temperatura exterior:

{outdoor_temp} °C


Modo:

{modos.get(mode,mode)}


Ventilador:

{fan_txt.get(fan,fan)}


HVAC:

{"Encendido" if hvac else "Apagado"}



ACCIONES PROGRAMADAS

60 s → alerta

120 s → reducción HVAC

180 s → apagado HVAC


Revise la sala.

"""


    em=EmailMessage()

    em["From"]=EMAIL
    em["To"]=DESTINO
    em["Subject"]=asunto

    em.set_content(
        cuerpo
    )


    context=ssl.create_default_context()


    try:

        with smtplib.SMTP_SSL(

            "smtp.gmail.com",
            465,
            context=context

        ) as smtp:


            smtp.login(

                EMAIL,
                PASSWORD

            )


            smtp.sendmail(

                EMAIL,
                DESTINO,
                em.as_string()

            )


        print(
            "[EMAIL] enviado"
        )


    except Exception as e:

        print(e)


# ===================================================
# SQLITE
# ===================================================

conn=sqlite3.connect(DB)

cursor=conn.cursor()


# ==========================================
# POSTGRESQL AWS
# ==========================================

try:

    pg_conn = psycopg2.connect(

        host="zero-leak-db-1.chod9zjutdtd.us-east-1.rds.amazonaws.com",

        port=5432,

        dbname="postgres",

        user="Zero_Leak",

        password="Zero_Leak",

        sslmode="verify-full",

        sslrootcert="/home/admin/Downloads/global-bundle.pem"

    )

    pg_cursor = pg_conn.cursor()

    print(
        "[AWS] conectado"
    )


except Exception as e:

    print(
        "[AWS ERROR]"
    )

    print(e)

    pg_conn = None
    pg_cursor = None


cursor.execute("""

CREATE TABLE IF NOT EXISTS hvac_data(

timestamp TEXT,
ambient REAL,
setpoint REAL,
outdoor REAL,
mode INTEGER,
fan INTEGER,
hvac INTEGER,
door INTEGER,
window INTEGER,
energy_stage INTEGER

)

""")


conn.commit()


# ===================================================
# REDUCCION HVAC
# ===================================================

def reduce_hvac():

    setpoint=read_reg(
        SETPOINT
    )

    mode=read_reg(
        MODE
    )


    delta=abs(
        outdoor_temp-setpoint
    )


    new_sp=setpoint


    client.write_register(

        address=12,
        value=1,
        device_id=SLAVE_ID

    )


    print(
        "[ACTION] Fan LOW"
    )


    if mode==1:

        new_sp=setpoint+(delta/3)


    elif mode==2:

        new_sp=setpoint-(delta/3)


    # Redondear a múltiplos de 0.5 °C
    new_sp = round(new_sp * 2) / 2


    client.write_register(

        address=6,
        value=int(new_sp * 10),
        device_id=SLAVE_ID

    )    

    print(

        f"[ACTION] Consigna {setpoint} -> {new_sp}"

    )


# ===================================================
# APAGADO HVAC
# ===================================================

def shutdown():

    client.write_register(

        address=ONOFF,
        value=0,
        device_id=SLAVE_ID

    )


    print(
        "[CRITICAL] HVAC OFF"
    )


# ===================================================
# LOGICA
# ===================================================

async def logic():

    global alert_sent
    global reduce_done
    global shutdown_done


    while True:


        door_time=0
        window_time=0


        if door_open:

            door_time=int(
                time.time()-door_start
            )


        if window_open:

            window_time=int(
                time.time()-window_start
            )


        timer=max(

            door_time,
            window_time

        )


        if not door_open and not window_open:

            alert_sent=False
            reduce_done=False
            shutdown_done=False


        print(

            "[TIMERS]",

            door_time,

            window_time

        )


        if timer>=60 and not alert_sent:

            print(
                "[LEVEL1]"
            )

            send_email()

            alert_sent=True


        if timer>=120 and not reduce_done:

            print(
                "[LEVEL2]"
            )

            reduce_hvac()

            reduce_done=True


        if timer>=180 and not shutdown_done:

            print(
                "[LEVEL3]"
            )

            shutdown()

            shutdown_done=True


        await asyncio.sleep(1)


# ===================================================
# GUARDAR DB
# ===================================================

async def save():

    while True:

        if outdoor_temp is None:

            print(
                "[BLE] esperando primera temperatura"
            )

            if last_ble_data is None:

                # todavía no ha llegado ninguna

                pass

            await asyncio.sleep(5)

            continue


        ambient=read_reg(
            AMBIENT_TEMP
        )

        setpoint=read_reg(
            SETPOINT_EFFECTIVE
        )

        mode=read_reg(
            MODE
        )

        fan=read_reg(
            FAN
        )

        hvac=read_reg(
            ONOFF
        )

        energy_stage = 0

        if shutdown_done:

            energy_stage = 3

        elif reduce_done:

            energy_stage = 2

        elif alert_sent:

            energy_stage = 1

        cursor.execute("""

            INSERT INTO hvac_data(

            timestamp,
            ambient,
            setpoint,
            outdoor,
            mode,
            fan,
            hvac,
            door,
            window,
            energy_stage

            )

            VALUES(?,?,?,?,?,?,?,?,?,?)

            """,(

            str(datetime.now()),
            ambient,
            setpoint,
            outdoor_temp,
            mode,
            fan,
            hvac,
            int(door_open),
            int(window_open),
            energy_stage

            ))


        conn.commit()
        # ======================================
        # ENVIAR A AWS
        # ======================================

        if pg_conn is not None:

            try:

                pg_cursor.execute("""

                INSERT INTO hvac_data(

                timestamp,
                ambient,
                setpoint,
                outdoor,

                mode,
                fan,
                hvac,

                door_state,
                window_state,
                energy_stage

                )

                VALUES(

                %s,%s,%s,%s,
                %s,%s,%s,
                %s,%s,%s

                )

                """,(

                datetime.now(),

                ambient,
                setpoint,
                outdoor_temp,

                mode,
                fan,
                hvac,

                bool(door_open),
                bool(window_open),
                energy_stage

                ))


                pg_conn.commit()


                print(
                    "[AWS] dato enviado"
                )


            except Exception as e:

                print(
                    "[AWS ERROR]"
                )

                print(e)

        print(f"""

Interior:{ambient}

Consigna:{setpoint}

Exterior:{outdoor_temp}

Modo:{mode}

Fan:{fan}

HVAC:{hvac}

Puerta:{door_open}

Ventana:{window_open}

""")


        await asyncio.sleep(5)
        
# ===================================================
# BLE TASK
# ===================================================

async def ble_task():

    global outdoor_temp

    while True:

        try:

            print("[BLE] intentando conectar")

            async with BleakClient(

                DEVICE_ADDRESS,

                timeout=30

            ) as ble:

                print(
                    "[BLE] conectado"
                )

                await ble.start_notify(

                    TEMP_UUID,

                    temp_callback

                )

                while True:

                    await asyncio.sleep(5)

        except Exception as e:

            print(
                "[BLE ERROR]"
            )

            print(e)

            outdoor_temp = None

            print(
                "[BLE] reintentando en 30 s"
            )

            await asyncio.sleep(30)

# ===================================================
# MAIN
# ===================================================

async def main():

    print(
        "Conectando Modbus..."
    )

    client.connect()

    print(
        "Modbus conectado"
    )

    init_sensor_states()

    await asyncio.gather(

        ble_task(),
        logic(),
        save()

    )


asyncio.run(main())