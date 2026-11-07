"""Coloca processos num Job Object do Windows com teto rígido de CPU.

Uso: python -I limitar_cpu.py <fator> <pid> [<pid> ...]
O teto é por máquina inteira: fator 4 em N CPUs lógicas equivale a 100/(N*4) %, ou seja,
uma única thread roda a 1/4 da velocidade de um núcleo. Todas as threads do processo dividem esse teto.
"""
import ctypes
import ctypes.wintypes as w
import os
import sys

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateJobObjectW.restype = w.HANDLE
kernel32.OpenProcess.restype = w.HANDLE
kernel32.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
kernel32.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]

JobObjectCpuRateControlInformation = 15
JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4
PROCESS_ALL = 0x1F0FFF


class Info(ctypes.Structure):
    _fields_ = [("ControlFlags", w.DWORD), ("CpuRate", w.DWORD)]


fator = float(sys.argv[1])
n = os.cpu_count()
taxa = max(1, round(10000 / (n * fator)))  # 10000 = 100% da máquina
job = kernel32.CreateJobObjectW(None, None)
if not job:
    raise OSError(ctypes.get_last_error(), "CreateJobObject")
info = Info(JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP, taxa)
if not kernel32.SetInformationJobObject(job, JobObjectCpuRateControlInformation, ctypes.byref(info), ctypes.sizeof(info)):
    raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
for pid in map(int, sys.argv[2:]):
    h = kernel32.OpenProcess(PROCESS_ALL, False, pid)
    if not h:
        raise OSError(ctypes.get_last_error(), f"OpenProcess {pid}")
    if not kernel32.AssignProcessToJobObject(job, h):
        raise OSError(ctypes.get_last_error(), f"AssignProcess {pid}")
print(f"cpus={n} taxa={taxa / 100:.2f}% pids={sys.argv[2:]}")
