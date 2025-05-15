# v0autodemo

# Run with: uvicorn api:app --reload to access API (FastAPI)

to access api: interview/latest/openai 

1strun.py is used for running to get auth.json
and autorun can be used therefaster

main_runner.py is the main app so you don't have to run FASTAPI

plan:
1). need some kind of UI that shows the final playwright result

curl -X POST https://00d6-68-239-60-198.ngrok-free.app/run -H "Content-Type: application/json" -d '{"prompt_override": "Create a modern landing page for a tech startup"}'


curl -X POST  https://v0-automation-71f16b24da1b.herokuapp.com/run_latest -H "Content-Type: application/json" -d '{}


