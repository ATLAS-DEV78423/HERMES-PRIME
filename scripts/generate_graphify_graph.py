"""Generate graphify knowledge graph and Obsidian vault for Hermes Prime."""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path("obsidian_graphify_custom").resolve()))

from graphify.ingestion import ingest_repo
from graphify.graph import Graph
from graphify.agents.structure_agent import StructureAgent
from graphify.agents.ast_agent import ASTAgent
from graphify.obsidian_writer import ObsidianWriter
from graphify.semantic import embed_texts, VectorStore


async def run_pipeline(repo_path: Path, out_dir: Path):
    files = ingest_repo(repo_path)
    graph = Graph()
    structure_agent = StructureAgent(graph)
    ast_agent = ASTAgent(graph)

    await asyncio.gather(
        structure_agent.run(files),
        ast_agent.run(files),
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    graph_json = graph.to_json()
    (out_dir / "graph.json").write_text(graph_json)
    print(f"Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"Saved to: {out_dir / 'graph.json'}")

    writer = ObsidianWriter(graph, out_dir)
    writer.write_vault()
    print(f"Obsidian vault written to: {out_dir / 'vault'}")

    embeddings_dir = out_dir / "embeddings"
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    try:
        nodes = list(graph.to_dict().get("nodes", []))
        texts, ids = [], []
        for n in nodes:
            parts = [str(n.get("name", "")), str(n.get("type", "")), str(n.get("path", ""))]
            p = n.get("path")
            if p:
                try:
                    fp = (repo_path / p).resolve()
                    if fp.exists() and fp.is_file():
                        parts.append(fp.read_text(encoding="utf-8")[:4000])
                except Exception:
                    pass
            text = "\n".join(x for x in parts if x)
            texts.append(text)
            ids.append(n.get("id"))
        if texts:
            embs = embed_texts(texts)
            store = VectorStore(embeddings_dir)
            store.add(ids, embs)
            print(f"Semantic index built: {len(ids)} vectors")
        else:
            VectorStore(embeddings_dir)
    except Exception as exc:
        print(f"[graphify] semantic index error: {exc}", file=sys.stderr)


if __name__ == "__main__":
    repo = Path(__file__).resolve().parent.parent
    out = repo / "graphify-out"
    asyncio.run(run_pipeline(repo, out))
