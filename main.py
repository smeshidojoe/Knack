import ctypes
import sys
from ctypes import wintypes

from knack.core.constants import INSTANCE_MUTEX

ERROR_ALREADY_EXISTS = 183

# Держим хэндл мьютекса в глобальной переменной: он должен жить до конца
# процесса, иначе сборщик закроет его и второй запуск пройдёт свободно.
_INSTANCE_MUTEX = None


def _is_only_instance():
    """True — мы единственный экземпляр; False — Knack уже запущен."""
    global _INSTANCE_MUTEX
    try:
        k = ctypes.windll.kernel32
        k.CreateMutexW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        _INSTANCE_MUTEX = k.CreateMutexW(None, False, INSTANCE_MUTEX)
        return k.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True         # ошибку ctypes не превращаем в запрет запуска


if __name__ == "__main__":
    from knack.core import updater

    # Самоприменение обновления: этот же exe (Knack-new.exe) запущен с флагом
    # --apply-update <старый_exe>. Ждёт выхода старого, подменяет его собой и
    # запускает. Обрабатываем ДО мьютекса — это не «второй экземпляр».
    if "--apply-update" in sys.argv:
        try:
            index = sys.argv.index("--apply-update")
            updater.apply_self_update(sys.argv[index + 1]
                                      if index + 1 < len(sys.argv) else "")
        except Exception:
            pass
        sys.exit(0)

    # Второй экземпляр повесил бы второй значок в трее и второй глобальный
    # хоткей — тихо выходим, панель уже работает.
    if not _is_only_instance():
        sys.exit(0)

    # Страховка: если с прошлого раза остался распакованный архив, применяем
    # то, что не заблокировано.
    try:
        updater.apply_pending()
        updater.cleanup_applied()
    except Exception:
        pass

    from knack.app import main
    sys.exit(main())
