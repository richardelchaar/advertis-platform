```mermaid
flowchart LR
  classDef svc fill:#eef,stroke:#77a,stroke-width:1px
  classDef ds fill:#efe,stroke:#7a7,stroke-width:1px
  classDef ext fill:#ffe,stroke:#aa7,stroke-width:1px

  subgraph Client
    U[User (Browser)]
  end

  subgraph HostApp[host_app (Streamlit)]
    HA[UI + Orchestration\n(get_final_response)]
    class HA svc
  end

  subgraph Inference[advertis_service (FastAPI)]
    API[FastAPI Endpoints\n/health · /v1/check-opportunity · /v1/get-response]
    AG[GamingAgent (LangGraph)\nDecision→Orchestrator→Host LLM]
    class API,AG svc
    API --> AG
  end

  subgraph Stores[Data Stores]
    PG[(PostgreSQL\nquestweaver_db)]
    RD[(Redis\nsafety + frequency gates)]
    CH[(ChromaDB\nad inventory embeddings)]
    OA[(OpenAI API\nLLM + embeddings)]
    class PG,RD,CH ds
    class OA ext
  end

  U --> HA
  HA <--> PG
  HA <--> API
  API <--> RD
  AG  <--> CH
  AG  <--> OA
  HA -. fallback LLM .-> OA