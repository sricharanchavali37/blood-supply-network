\# Smart Blood Network Backend



FastAPI backend for a blood supply coordination system.



Core modules:

\- Authentication (JWT)

\- Hospital management

\- Blood inventory tracking

\- Shortage prediction

\- Decision engine

\- Donor management

\- Alert system

\- Analytics

\- Event logging

## System Architecture

!\[Architecture](docs/architecture.png)



\## Database ER Diagram

!\[Database ER](docs/database\_er.png)





Integration testing:

Run the automated pipeline test:



python test\_pipeline.py



Server start:



uvicorn app.main:app --reload



Docs:

http://127.0.0.1:8000/docs




