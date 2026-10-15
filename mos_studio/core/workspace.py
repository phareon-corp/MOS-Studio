"""Pasta de trabalho, projetos e índice de execuções.

Projetos e execuções moram **fora** da pasta do programa, numa pasta de
trabalho escolhida pelo usuário (``~/Simulações`` por padrão). A instalação
fica só com o programa e os motores; o trabalho do usuário fica com o usuário.

As execuções da versão anterior continuam em ``resultados/``, dentro do
repositório, e podem ser importadas para o índice sem serem movidas.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import config, paths
from .recipe import Step

PROJECT_SUFFIX = ".mosproj"
RUN_META = "execucao.json"


# ── pastas ────────────────────────────────────────────────────────────────

def default_working_dir() -> Path:
    """``~/Simulações`` (ou ``~/Simulacoes`` se o sistema não aceitar acento)."""
    try:
        caminho = Path.home() / "Simulações"
        caminho.name.encode("utf-8")
        return caminho
    except UnicodeError:                                  # pragma: no cover
        return Path.home() / "Simulacoes"


def working_dir() -> Path:
    """Pasta de trabalho em vigor, criada se necessário."""
    salvo = config.get("pasta_trabalho", "")
    caminho = Path(salvo).expanduser() if salvo else default_working_dir()
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def set_working_dir(caminho: str | Path) -> Path:
    """Troca a pasta de trabalho e devolve a nova."""
    novo = Path(caminho).expanduser()
    novo.mkdir(parents=True, exist_ok=True)
    config.set("pasta_trabalho", str(novo))
    return novo


def runs_dir() -> Path:
    """Onde ficam as execuções, uma subpasta por simulação."""
    d = working_dir() / "execucoes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def legacy_results_dir() -> Path:
    """Pasta ``resultados/`` da versão anterior, ao lado do programa."""
    return paths.RESULTS_DIR


def slug(texto: str, limite: int = 40) -> str:
    """Nome de arquivo seguro a partir de um título."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", texto)[:limite].strip("_") or "simulacao"


# ── projeto ───────────────────────────────────────────────────────────────

@dataclass
class Project:
    """Um projeto: a receita, o título do deck e as anotações.

    Um projeto guarda as **duas** dimensões ao mesmo tempo: a receita 1-D em
    ``steps`` e a 2-D em ``mesh``/``steps4``/``models``. É de propósito —
    trocar de dimensão no cabeçalho não pode apagar o trabalho da outra, e um
    processo costuma ser estudado em 1-D antes de virar seção transversal.
    ``dimension`` só diz qual das duas está em foco.
    """

    name: str = "Novo projeto"
    title: str = "NOVA SIMULACAO"
    steps: list[Step] = field(default_factory=list)
    notes: str = ""
    device: dict[str, Any] = field(default_factory=dict)
    oxidation: dict[str, Any] = field(default_factory=dict)
    #: ``"1d"`` (SUPREM-III) ou ``"2d"`` (SUPREM-IV).
    dimension: str = "1d"
    #: A malha 2-D: ``{"x": [{"loc":…, "spacing":…}], "y": [...],
    #: "material": "silicon"}``. Vazio = a malha padrão do exam5.
    mesh: dict[str, Any] = field(default_factory=dict)
    #: Etapas da receita 2-D, no mesmo formato de ``steps``.
    steps4: list[Step] = field(default_factory=list)
    #: Só os parâmetros de modelo que o usuário alterou (ver
    #: :class:`mos_studio.core.models4.Models4`).
    models: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None
    dirty: bool = False

    # ── criação ───────────────────────────────────────────────────────────

    @classmethod
    def from_recipe(cls, recipe) -> "Project":
        """Projeto novo a partir de uma receita da biblioteca."""
        return cls(name=f"{recipe.name} {recipe.emphasis}".strip(),
                   title=recipe.title, steps=recipe.build())

    @classmethod
    def from_deck(cls, texto: str, nome: str = "") -> "Project":
        """Projeto novo a partir de um deck ``.IN`` importado."""
        from .deck import parse_in_file
        titulo, passos = parse_in_file(texto)
        etapas = [Step(p["type"], dict(p["params"])) for p in passos
                  if p["type"] != "PLOT"]
        return cls(name=nome or titulo.title() or "Deck importado",
                   title=titulo, steps=etapas)

    # ── disco ─────────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Projeto em JSON.

        O ``formato`` subiu para 2 com a chegada do 2-D. Os arquivos de
        formato 1 continuam abrindo: as chaves novas simplesmente faltam, e
        :meth:`from_dict` as preenche com o padrão.
        """
        return {
            "formato": 2,
            "nome": self.name,
            "titulo": self.title,
            "anotacoes": self.notes,
            "dispositivo": self.device,
            "oxidacao": self.oxidation,
            "etapas": [{"tipo": s.type, "parametros": s.params} for s in self.steps],
            "dimensao": self.dimension,
            "malha": self.mesh,
            "etapas2d": [{"tipo": s.type, "parametros": s.params}
                         for s in self.steps4],
            "modelos": self.models,
        }

    @classmethod
    def from_dict(cls, dados: dict[str, Any], path: Path | None = None) -> "Project":
        def ler(chave: str) -> list[Step]:
            return [Step(e.get("tipo", ""), dict(e.get("parametros", {})))
                    for e in dados.get(chave, [])]

        dim = str(dados.get("dimensao", "1d")).lower()
        return cls(name=dados.get("nome", "Projeto"),
                   title=dados.get("titulo", "SIMULACAO"),
                   steps=ler("etapas"),
                   notes=dados.get("anotacoes", ""),
                   device=dict(dados.get("dispositivo", {})),
                   oxidation=dict(dados.get("oxidacao", {})),
                   dimension=dim if dim in ("1d", "2d") else "1d",
                   mesh=dict(dados.get("malha", {})),
                   steps4=ler("etapas2d"),
                   models=dict(dados.get("modelos", {})),
                   path=path)

    def save(self, path: Path | None = None) -> Path:
        """Grava o projeto. Sem caminho, usa o atual ou cria um na pasta."""
        destino = Path(path) if path else self.path
        if destino is None:
            destino = working_dir() / f"{slug(self.name)}{PROJECT_SUFFIX}"
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(destino.suffix + ".tmp")
        temporario.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8")
        temporario.replace(destino)
        self.path = destino
        self.dirty = False
        return destino

    @classmethod
    def load(cls, path: str | Path) -> "Project":
        """Lê um projeto do disco."""
        p = Path(path)
        return cls.from_dict(json.loads(p.read_text(encoding="utf-8")), p)


def list_projects() -> list[Path]:
    """Projetos na pasta de trabalho, do mais recente para o mais antigo."""
    return sorted(working_dir().glob(f"*{PROJECT_SUFFIX}"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


# ── execuções ─────────────────────────────────────────────────────────────

@dataclass
class RunRecord:
    """Uma execução guardada em disco."""

    path: Path
    name: str = ""
    when: datetime.datetime | None = None
    status: str = "ok"             # ok | parcial | erro | cancelada
    elapsed: float = 0.0
    engine: str = "SUPREM-III"
    note: str = ""
    legacy: bool = False
    number: int = 0

    @property
    def when_text(self) -> str:
        """“hoje 14:32 · 4,8 s”, como no arquivo de design."""
        if self.when is None:
            return ""
        hoje = datetime.date.today()
        dia = self.when.date()
        if dia == hoje:
            quando = f"hoje {self.when:%H:%M}"
        elif (hoje - dia).days == 1:
            quando = f"ontem {self.when:%H:%M}"
        else:
            quando = f"{self.when:%d/%m %H:%M}"
        if self.elapsed:
            return f"{quando} · {self.elapsed:.1f} s".replace(".", ",")
        return quando

    def deck(self) -> str:
        """O deck que foi enviado ao motor nesta execução."""
        arquivo = self.path / "INPUT.IN"
        if arquivo.exists():
            return arquivo.read_text(encoding="latin1", errors="replace")
        return ""

    def outputs(self) -> dict[str, str]:
        """Arquivos de saída desta execução, pelo nome."""
        saidas = {}
        for f in sorted(self.path.iterdir()):
            if f.is_file() and f.suffix.upper() in (".OUT", ".TXT", ".LST"):
                if f.name.upper() == "INPUT.IN":
                    continue
                saidas[f.name] = f.read_text(encoding="latin1", errors="replace")
        return saidas

    def profile(self) -> list[tuple[float, float]]:
        """Perfil de dopagem desta execução, se alguma saída tiver a tabela."""
        from .parsers import parse_out_file
        for nome, raw in self.outputs().items():
            dados = parse_out_file(raw)
            if dados:
                return dados
        return []

    def layers(self) -> list[tuple[str, float]]:
        """Camadas desta execução."""
        from .parsers import parse_layers
        for raw in self.outputs().values():
            camadas = parse_layers(raw)
            if camadas:
                return camadas
        return []

    def write_meta(self) -> None:
        """Grava os metadados ao lado dos arquivos de saída."""
        dados = {"nome": self.name, "status": self.status,
                 "duracao": self.elapsed, "motor": self.engine,
                 "anotacao": self.note,
                 "quando": (self.when or datetime.datetime.now()).isoformat()}
        try:
            (self.path / RUN_META).write_text(
                json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def rename(self, novo: str) -> None:
        self.name = novo
        self.write_meta()

    def set_note(self, texto: str) -> None:
        self.note = texto
        self.write_meta()

    def delete(self) -> bool:
        """Apaga a execução do disco."""
        try:
            shutil.rmtree(self.path)
            return True
        except OSError:
            return False


def _read_record(pasta: Path, legacy: bool = False) -> RunRecord | None:
    """Lê uma execução de uma pasta, inferindo o que não estiver gravado."""
    if not pasta.is_dir():
        return None
    meta_path = pasta / RUN_META
    dados: dict[str, Any] = {}
    if meta_path.exists():
        try:
            dados = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dados = {}

    quando = None
    if dados.get("quando"):
        try:
            quando = datetime.datetime.fromisoformat(dados["quando"])
        except ValueError:
            quando = None
    if quando is None:
        quando = datetime.datetime.fromtimestamp(pasta.stat().st_mtime)

    nome = dados.get("nome") or _infer_name(pasta)
    registro = RunRecord(path=pasta, name=nome, when=quando,
                         status=dados.get("status", ""),
                         elapsed=float(dados.get("duracao", 0.0) or 0.0),
                         engine=dados.get("motor", "SUPREM-III"),
                         note=dados.get("anotacao", ""),
                         legacy=legacy)
    if not registro.status:
        registro.status = _infer_status(registro)
    return registro


def _infer_name(pasta: Path) -> str:
    """Nome legível a partir do deck ou do nome da pasta."""
    entrada = pasta / "INPUT.IN"
    if entrada.exists():
        from .deck import deck_title
        titulo = deck_title(entrada.read_text(encoding="latin1", errors="replace"), "")
        if titulo:
            return titulo
    nome = re.sub(r"_?\d{8}_\d{6}$", "", pasta.name)
    return nome.replace("_", " ").strip() or pasta.name


def _infer_status(registro: RunRecord) -> str:
    """Estado de uma execução antiga, a partir do que ela deixou em disco."""
    saidas = registro.outputs()
    if not saidas:
        return "erro"
    texto = " ".join(saidas.values()).lower()
    if "error number" in texto:
        return "erro"
    return "ok" if registro.profile() else "parcial"


def list_runs(include_legacy: bool = True) -> list[RunRecord]:
    """Todas as execuções conhecidas, da mais recente para a mais antiga."""
    registros: list[RunRecord] = []
    for pasta in runs_dir().iterdir():
        r = _read_record(pasta)
        if r is not None:
            registros.append(r)
    if include_legacy and config.get("importar_legado", False):
        legado = legacy_results_dir()
        if legado.exists():
            for pasta in legado.iterdir():
                r = _read_record(pasta, legacy=True)
                if r is not None:
                    registros.append(r)
    registros.sort(key=lambda r: r.when or datetime.datetime.min, reverse=True)
    for i, r in enumerate(reversed(registros), start=1):
        r.number = i
    return registros


def count_legacy_runs() -> int:
    """Quantas execuções a versão anterior deixou em ``resultados/``."""
    legado = legacy_results_dir()
    if not legado.exists():
        return 0
    return sum(1 for p in legado.iterdir() if p.is_dir())


def legacy_imported() -> bool:
    """Se as execuções antigas já foram trazidas para o índice."""
    return bool(config.get("importar_legado", False))


def import_legacy() -> int:
    """Passa a listar as execuções antigas, sem movê-las de lugar.

    Elas continuam em ``resultados/``; só entram no índice. Mover 107 pastas
    seria arriscar o histórico sem necessidade.
    """
    total = count_legacy_runs()
    config.set("importar_legado", True)
    return total


def record_dir(out_dir, *, name: str = "", status: str = "ok",
               elapsed: float = 0.0,
               engine: str = "SUPREM-III") -> RunRecord | None:
    """Grava os metadados de uma pasta de execução já escrita em disco."""
    if not out_dir:
        return None
    pasta = Path(out_dir)
    if not pasta.exists():
        return None
    registro = RunRecord(path=pasta, name=name or _infer_name(pasta),
                         when=datetime.datetime.now(), status=status,
                         elapsed=elapsed, engine=engine)
    registro.write_meta()
    return registro


def record_run(result, *, name: str = "", status: str = "ok",
               engine: str = "SUPREM-III") -> RunRecord | None:
    """Grava os metadados de uma execução recém-terminada."""
    if result is None or result.out_dir is None:
        return None
    return record_dir(result.out_dir, name=name, status=status,
                      elapsed=result.elapsed, engine=engine)
