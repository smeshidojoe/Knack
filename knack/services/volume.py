"""
Громкость системы.

Ползунок в «Музыке» двигает общий уровень вывода — тот же, что и системный
регулятор в трее. Громкость отдельного приложения Windows тоже умеет, но её
пришлось бы искать по сессиям и заново привязывать при каждой смене источника,
а ползунок в панели полезен и тогда, когда SMTC молчит.

Идём через ctypes прямо в COM: pycaw и comtypes ради трёх вызовов тянуть в
сборку не хочется. Интерфейсы вызываются по номеру метода в таблице — порядок
задан в mmdeviceapi.h и endpointvolume.h и меняться не может, иначе поломались
бы все скомпилированные программы.
"""

import ctypes
from ctypes import POINTER, byref, c_float, c_void_p

from PySide6.QtCore import QObject

from ..core import logbook

ole32 = ctypes.windll.ole32

CLSCTX_ALL = 0x17
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = -2147417850

E_RENDER = 0            # устройство вывода
ROLE_MULTIMEDIA = 1     # роль «музыка и видео»

CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"

# Номера методов в таблицах интерфейсов (первые три — от IUnknown).
DEV_ENUM_GET_DEFAULT = 4          # IMMDeviceEnumerator::GetDefaultAudioEndpoint
DEVICE_ACTIVATE = 3               # IMMDevice::Activate
VOL_SET_SCALAR = 7                # IAudioEndpointVolume::SetMasterVolumeLevelScalar
VOL_GET_SCALAR = 9                # ::GetMasterVolumeLevelScalar
VOL_SET_MUTE = 14
VOL_GET_MUTE = 15
IUNKNOWN_RELEASE = 2


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(self))


def _method(ptr, index, *argtypes):
    """Метод COM-интерфейса по номеру в таблице."""
    table = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    return proto(table[index])


def ensure_com():
    """
    Инициализирует COM в текущем потоке. Зовут все, кто ходит в аудио-API.

    RPC_E_CHANGED_MODE значит, что поток уже в другой модели — не помеха: COM в
    нём инициализирован, вызовы пройдут.
    """
    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != RPC_E_CHANGED_MODE:
        raise OSError("CoInitializeEx 0x%08X" % (hr & 0xFFFFFFFF))
    return True


def _release(ptr):
    if ptr:
        _method(ptr, IUNKNOWN_RELEASE)(ptr)


class VolumeService(QObject):
    """Общий уровень вывода: чтение, запись, выключение звука."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._volume = None
        self._broken = False

    # --- подключение ------------------------------------------------------ #

    def _endpoint(self):
        """Интерфейс громкости устройства вывода. Достаём один раз и держим."""
        if self._volume or self._broken:
            return self._volume
        try:
            ensure_com()
            enumerator = c_void_p()
            hr = ole32.CoCreateInstance(byref(GUID(CLSID_MMDeviceEnumerator)),
                                        None, CLSCTX_ALL,
                                        byref(GUID(IID_IMMDeviceEnumerator)),
                                        byref(enumerator))
            if hr < 0 or not enumerator:
                raise OSError("CoCreateInstance 0x%08X" % (hr & 0xFFFFFFFF))

            device = c_void_p()
            try:
                get_default = _method(enumerator, DEV_ENUM_GET_DEFAULT,
                                      ctypes.c_int, ctypes.c_int,
                                      POINTER(c_void_p))
                hr = get_default(enumerator, E_RENDER, ROLE_MULTIMEDIA,
                                 byref(device))
                if hr < 0 or not device:
                    raise OSError("GetDefaultAudioEndpoint 0x%08X"
                                  % (hr & 0xFFFFFFFF))

                volume = c_void_p()
                activate = _method(device, DEVICE_ACTIVATE, POINTER(GUID),
                                   ctypes.c_uint, c_void_p, POINTER(c_void_p))
                hr = activate(device, byref(GUID(IID_IAudioEndpointVolume)),
                              CLSCTX_ALL, None, byref(volume))
                if hr < 0 or not volume:
                    raise OSError("Activate 0x%08X" % (hr & 0xFFFFFFFF))
                self._volume = volume
            finally:
                _release(device)
                _release(enumerator)
        except Exception:
            # Без звуковой карты (или в сессии без устройства вывода) громкости
            # нет вовсе — ползунок тогда просто не показываем.
            logbook.exc("громкость: не удалось подключиться")
            self._broken = True
            self._volume = None
        return self._volume

    def available(self):
        return self._endpoint() is not None

    def _forget(self):
        """Устройство сменили — интерфейс протух, возьмём новый при следующем
        обращении."""
        _release(self._volume)
        self._volume = None

    # --- чтение и запись --------------------------------------------------- #

    def level(self):
        """Громкость долей 0..1. None — спросить не у кого."""
        ptr = self._endpoint()
        if not ptr:
            return None
        value = c_float()
        hr = _method(ptr, VOL_GET_SCALAR, POINTER(c_float))(ptr, byref(value))
        if hr < 0:
            self._forget()
            return None
        return max(0.0, min(1.0, float(value.value)))

    def muted(self):
        ptr = self._endpoint()
        if not ptr:
            return False
        state = ctypes.c_int()
        hr = _method(ptr, VOL_GET_MUTE, POINTER(ctypes.c_int))(ptr, byref(state))
        if hr < 0:
            self._forget()
            return False
        return bool(state.value)

    def set_level(self, value):
        ptr = self._endpoint()
        if not ptr:
            return False
        value = max(0.0, min(1.0, float(value)))
        hr = _method(ptr, VOL_SET_SCALAR, c_float, POINTER(GUID))(
            ptr, c_float(value), None)
        if hr < 0:
            self._forget()
            return False
        # Двигая ползунок, звук заодно включаем: тянуть громкость у выключенного
        # звука и не слышать результата — худшее, что может сделать регулятор.
        if value > 0 and self.muted():
            self.set_muted(False)
        return True

    def set_muted(self, muted):
        ptr = self._endpoint()
        if not ptr:
            return False
        hr = _method(ptr, VOL_SET_MUTE, ctypes.c_int, POINTER(GUID))(
            ptr, 1 if muted else 0, None)
        if hr < 0:
            self._forget()
            return False
        return True

    def toggle_mute(self):
        self.set_muted(not self.muted())

    def shutdown(self):
        self._forget()
