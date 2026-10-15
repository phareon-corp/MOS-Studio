"""Conversa com a VM Windows de testes pelo ``qemu-guest-agent``.

Esta VM é deliberadamente isolada: não enxerga o host pela rede, e a pasta
compartilhada só existe enquanto há uma sessão RDP aberta. Para automatizar
a compilação e os testes do pacote de Windows sobra o guest-agent, que
aceita rodar programas e escrever arquivos no convidado. É só isso que este
módulo embrulha.

Não é parte do MOS-Studio: é ferramenta de quem empacota.
"""

from __future__ import annotations

import base64
import json
import subprocess
import time
from pathlib import Path

URI = "qemu:///session"
VM = "office"

#: Bytes por chamada de escrita. O comando vai pela linha de comando do virsh
#: como um único argumento, e o Linux limita cada argumento a 128 kB
#: (MAX_ARG_STRLEN). Em base64 cada pedaço cresce um terço, então 48 kB de
#: dados viram 64 kB de argumento — metade do teto, com folga para o resto do
#: JSON. Medido: com 96 kB o execve falha com "Argument list too long".
PEDACO = 48 * 1024


class ErroDaVM(RuntimeError):
    """O virsh ou o agente dentro do convidado recusou o pedido."""


def ligada() -> bool:
    """Diz se a VM está executando."""
    saida = subprocess.run(["virsh", "-c", URI, "domstate", VM],
                           capture_output=True, text=True)
    return saida.stdout.strip() in ("running", "executando")


def ligar(espera: float = 180.0) -> None:
    """Sobe a VM, se preciso, e espera o agente responder."""
    if not ligada():
        subprocess.run(["virsh", "-c", URI, "start", VM],
                       capture_output=True, text=True, check=True)
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        # Chama o virsh direto, e não agente(): aquele religa a VM quando ela
        # está parada, e aqui isso seria uma recursão sem fim.
        saida = subprocess.run(
            ["virsh", "-c", URI, "qemu-agent-command", VM,
             '{"execute":"guest-ping"}'],
            capture_output=True, text=True, timeout=60)
        if saida.returncode == 0:
            return
        time.sleep(2)
    raise ErroDaVM("o agente da VM não respondeu")


#: Quantas vezes insistir quando o agente não responde no prazo do virsh.
#: O virsh espera 5 s por resposta e, numa VM que acabou de acordar ou está
#: no meio de uma simulação, isso estoura de vez em quando sem que nada
#: tenha dado errado — o comando seguinte passa. Só os erros listados em
#: :data:`RECUPERAVEIS` são repetidos; qualquer outra recusa sobe na hora.
TENTATIVAS = 6

#: Pedaços de mensagem do virsh que valem uma segunda tentativa.
#:
#: "timed out" é o prazo de 5 s do próprio virsh. "not running" / "não está
#: em execução" é a VM congelada: esta máquina tem um vigia
#: (``office-vm/vigia.sh``) que dá ``managedsave`` depois de dois minutos sem
#: nenhum cliente RDP aberto, e um build ou um teste demora mais que isso.
#: O ``managedsave`` guarda o estado inteiro, então religar devolve a VM
#: exatamente onde parou — inclusive processos no meio da execução. Para quem
#: chama, é só uma pausa.
RECUPERAVEIS = ("timed out", "not running", "não está em execução",
                "nao esta em execucao")


def agente(pedido: dict, timeout: float = 180.0) -> dict:
    """Manda um comando ao guest-agent e devolve a resposta decodificada."""
    corpo = json.dumps(pedido)
    for tentativa in range(TENTATIVAS):
        saida = subprocess.run(
            ["virsh", "-c", URI, "qemu-agent-command", VM, corpo],
            capture_output=True, text=True, timeout=timeout)
        if saida.returncode == 0:
            return json.loads(saida.stdout)
        erro = saida.stderr.strip() or "virsh falhou"
        recuperavel = any(m in erro for m in RECUPERAVEIS)
        if not recuperavel or tentativa == TENTATIVAS - 1:
            raise ErroDaVM(erro)
        if not ligada():
            ligar()
        else:
            time.sleep(2)
    raise AssertionError("inalcançável")


def rodar(programa: str, *argumentos: str, espera: float = 3600.0,
          cwd: str | None = None) -> tuple[int, str, str]:
    """Roda um programa no Windows e devolve (código, saída, erro)."""
    pedido: dict = {"path": programa, "arg": list(argumentos),
                    "capture-output": True}
    if cwd is not None:
        pedido["env"] = [f"MOSCWD={cwd}"]
    pid = agente({"execute": "guest-exec", "arguments": pedido})["return"]["pid"]
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        r = agente({"execute": "guest-exec-status",
                    "arguments": {"pid": pid}})["return"]
        if r.get("exited"):
            def texto(chave: str) -> str:
                dados = r.get(chave)
                if not dados:
                    return ""
                return base64.b64decode(dados).decode("utf-8", "replace")
            return r.get("exitcode", 0), texto("out-data"), texto("err-data")
        time.sleep(0.5)
    raise TimeoutError(f"{programa} não terminou em {espera:.0f} s")


def powershell(comando: str, espera: float = 3600.0) -> str:
    """Roda um comando do PowerShell no Windows e devolve a saída junta.

    O comando vai em base64/UTF-16LE (``-EncodedCommand``) para não ter de
    adivinhar como o PowerShell, o cmd e o agente tratariam aspas, acentos e
    quebras de linha pelo caminho.
    """
    # A saída vem em UTF-8 porque o preâmbulo manda: sem isso o PowerShell
    # entrega o texto na página de código do console (1252 por aqui) e todo
    # acento do relatório chega trocado.
    preambulo = ("[Console]::OutputEncoding = "
                 "[System.Text.Encoding]::UTF8\n"
                 "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
                 "$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'\n")
    codificado = base64.b64encode(
        (preambulo + comando).encode("utf-16-le")).decode()
    _, saida, erro = rodar("powershell.exe", "-NoProfile",
                           "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", codificado, espera=espera)
    return saida + _sem_clixml(erro)


def _sem_clixml(erro: str) -> str:
    """Tira do stderr o XML de progresso que o PowerShell despeja lá.

    Quando roda sem console, o PowerShell serializa barras de progresso e
    outros objetos no stderr como CLIXML — inclusive um "Preparando módulos
    para primeiro uso" que não é erro nenhum. Só o que vem antes do
    ``#< CLIXML`` é mensagem de verdade.
    """
    corte = erro.find("#< CLIXML")
    return erro if corte < 0 else erro[:corte]


def enviar_arquivo(local: Path, remoto: str) -> int:
    """Grava um arquivo do host no caminho remoto do Windows."""
    dados = Path(local).read_bytes()
    alca = agente({"execute": "guest-file-open",
                   "arguments": {"path": remoto, "mode": "wb"}})["return"]
    try:
        for i in range(0, len(dados), PEDACO):
            agente({"execute": "guest-file-write", "arguments": {
                "handle": alca,
                "buf-b64": base64.b64encode(dados[i:i + PEDACO]).decode()}})
    finally:
        agente({"execute": "guest-file-close", "arguments": {"handle": alca}})
    return len(dados)


def baixar_arquivo(remoto: str, local: Path) -> int:
    """Traz um arquivo do Windows para o host.

    Vem pelo PowerShell em base64, e não por ``guest-file-read``: assim o
    pedaço é escolhido aqui, e arquivos grandes (um instalador tem dezenas de
    megabytes) não dependem do limite de uma leitura só do agente.
    """
    remoto_ps = remoto.replace("'", "''")
    tamanho = int(powershell(
        f"(Get-Item -LiteralPath '{remoto_ps}').Length").strip())
    # 3 MB por volta: em base64 dá 4 MB de saída, que o agente devolve de uma
    # vez sem engasgar, e um instalador inteiro vem em poucas chamadas.
    bloco = 3 * 1024 * 1024
    with open(local, "wb") as destino:
        for inicio in range(0, max(tamanho, 1), bloco):
            quanto = min(bloco, tamanho - inicio)
            if quanto <= 0:
                break
            texto = powershell(
                f"$f=[IO.File]::OpenRead('{remoto_ps}');"
                f"$f.Position={inicio};"
                f"$b=New-Object byte[] {quanto};"
                f"$lido=0; while($lido -lt {quanto})"
                f"{{ $n=$f.Read($b,$lido,{quanto}-$lido);"
                f"  if($n -le 0){{break}}; $lido+=$n }};"
                f"$f.Close();"
                f"[Convert]::ToBase64String($b,0,$lido)")
            destino.write(base64.b64decode("".join(texto.split())))
    return Path(local).stat().st_size


def enviar_pasta(origem: Path, destino: str) -> tuple[int, int]:
    """Copia uma pasta inteira. Devolve (nº de arquivos, bytes)."""
    origem = Path(origem)
    destino = destino.rstrip("\\")
    arquivos = sorted(p for p in origem.rglob("*") if p.is_file())
    pastas = sorted({str(p.parent.relative_to(origem)) for p in arquivos})
    criar = "".join(
        f"New-Item -ItemType Directory -Force -Path "
        f"'{destino}\\{d.replace('/', chr(92))}' | Out-Null;"
        for d in pastas if d != ".")
    powershell(f"New-Item -ItemType Directory -Force -Path '{destino}'"
               f" | Out-Null;{criar}")
    total = 0
    for f in arquivos:
        rel = str(f.relative_to(origem)).replace("/", "\\")
        total += enviar_arquivo(f, f"{destino}\\{rel}")
    return len(arquivos), total
