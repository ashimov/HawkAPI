# Dependency Injection

HawkAPI provides a constructor-based DI system with scoped lifetimes.

## Basic Usage

```python
from hawkapi import Depends, HawkAPI

app = HawkAPI()

async def get_db():
    db = await connect()
    try:
        yield db
    finally:
        await db.close()

@app.get("/users")
async def list_users(db=Depends(get_db)):
    return await db.fetch_all("SELECT * FROM users")
```

## DI Container

Register and resolve services globally:

```python
from hawkapi import Container, Depends, HawkAPI

container = Container()
container.register(Database, factory=create_database)

app = HawkAPI(container=container)

@app.get("/items")
async def list_items(db: Database = Depends()):
    return await db.fetch_all("SELECT * FROM items")
```

## Generator Dependencies

Use `yield` to run cleanup after the response is sent:

```python
async def get_session():
    session = Session()
    try:
        yield session
    finally:
        await session.close()
```

## Nested Dependencies

Dependencies can depend on other dependencies:

```python
async def get_db():
    yield Database()

async def get_user_repo(db=Depends(get_db)):
    return UserRepository(db)

@app.get("/users")
async def list_users(repo=Depends(get_user_repo)):
    return await repo.find_all()
```
