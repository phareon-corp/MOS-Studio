"""MOSIM — simulador de dispositivo MOS aberto, compatível com decks do MINIMOS 6.1.

Lê os mesmos arquivos de entrada do MINIMOS (diretivas DEVICE, BIAS, STEP,
PROFILE, IMPLANT, INTERFACE, OPTION, MOBILITY…) e grava saídas no mesmo
formato (.out, .ref, .iv). Os modelos físicos são os descritos no manual do
MINIMOS 6; o código é próprio.
"""
__version__ = "0.1"
