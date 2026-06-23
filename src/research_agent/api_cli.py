"""Console-script wrapper: `research-agent-api` launches the FastAPI backend."""

import uvicorn


def main():
    uvicorn.run("research_agent.api:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
