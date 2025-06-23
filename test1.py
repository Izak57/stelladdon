from secrets import token_urlsafe
from fastapi import FastAPI
from stelladdon import StellaMongo, StellAppMaster, FromDB, APIObject, Service, Context
from pydantic import BaseModel, Field
from typing import Annotated



client = StellaMongo("mongodb://localhost:27017")
db = client.get_database("stelladdon-test")



class User(APIObject):
    id: str = Field(default_factory=lambda: token_urlsafe(16))
    username: str
    email: str
    level: int = 1

    def get_api_data(self, mode):
        if mode == "public":
            return {
                "id": self.id,
                "username": self.username,
                "level": self.level
            }
        
        elif mode == "personal":
            return {
                "id": self.id,
                "username": self.username,
                "email": self.email,
                "level": self.level
            }

UserTable = db.create_table(User, "users", primary_key="id")



fapp = FastAPI()
app = StellAppMaster(fapp)



CheckAdmin = Service("CheckAdmin")

@CheckAdmin.before
async def check_admin(stella: Context, token: str):
    is_admin = token == "admin"
    stella.states["is_admin"] = is_admin

    if not is_admin:
        # raise StellaAPIError("You are not an admin!", status_code=403)
        print("You are not an admin!")


@CheckAdmin.after
async def check_admin_after(stella: Context, response):
    if stella.states.get("is_admin", False):
        print(f"Admin check passed")
    else:
        print(f"Admin check failed")

    print("ADMIN RESP:", response)
    return response



@app.route("GET", "/admin/test/", [CheckAdmin])
async def admlin_test(stella: Context, name: str):
    negation = "not " if not stella.states.get("is_admin", False) else ""
    return f"you are {negation}an admin, {name}!"



@app.route("GET", "/users/post/{name}")
async def post_user(name: str):
    user = User(username=name, email=f"{name}@example.com")
    UserTable.insert(user)
    return user


@app.route("GET", "/users/{id}")
async def get_user(id: Annotated[User, FromDB(UserTable)]):
    print(id)
    return id


@app.route("GET", "/users/byname/{username}")
async def get_user_by_name(username: Annotated[User, FromDB(UserTable, multiple=True)]):
    print(username)
    return username


@app.route("GET", "/users")
async def get_user():
    return UserTable.find({})



from uvicorn import run

if __name__ == "__main__":
    run("test:fapp", host="0.0.0.0", port=5000, reload=True)
