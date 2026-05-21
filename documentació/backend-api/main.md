# `app/backend/api/main.py`

Punt d'entrada de FastAPI. Munta els routers de `routes/search.py` i `routes/cercador.py`, configura CORS i defineix un `lifespan` que pre-escalfa tots els recursos lents abans d'acceptar trànsit.

## Funcions

| Nom | Què fa |
| --- | --- |
| `_flag(name)` | Lectura booleana d'una variable d'entorn (`"1"`/`"true"`/`"yes"`/`"on"`). |
| `_maybe_recompute()` | Si `RECOMPUTE_2D=1` o `RECOMPUTE_META=1`, executa el pas corresponent del data pipeline abans d'arrancar el servidor i invalida les caches. |
| `_warm_encoder()` | Crida `encode_query("warmup")` perquè el primer forward del model bge-m3 ja s'hagi pagat abans del primer request d'usuari. |
| `_safe_call(fn, label)` | Wrapper de log que captura excepcions del pre-warm sense fer caure el procés. |
| `lifespan(app)` | Hook d'arrencada de FastAPI. En aquest ordre: 1) carrega `load_visible_songs` + `get_all_projections_2d`; 2) construeix l'`get_visible_index` dens; 3) carrega el model + warm-up; 4) en segon pla, construeix l'índex del cercador (`cercador_index.prewarm`). |

## Variables d'entorn

| Flag | Efecte |
| --- | --- |
| `RECOMPUTE_2D=1` | Reexecuta `data_pipeline.step6_project_2d` abans d'arrancar. |
| `RECOMPUTE_META=1` | Reexecuta `data_pipeline.step5_build_meta`. |

## Endpoints

L'arrel `GET /` retorna `{"status": "ok", "message": "..."}`. La resta vénen dels routers a `routes/`.

## Per què hi ha pre-warm

El primer `/api/filter` ha de pagar només la cosinusada de la query. Sense `lifespan`, el cost del `transformers` (~30s) i de la construcció de l'índex dens (~15s) caurien al primer usuari.
