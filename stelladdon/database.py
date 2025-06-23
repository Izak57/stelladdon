from typing import Generic, Callable, Type, Any

from pymongo import MongoClient

from .typin import TableModelT
from .utils import _pretty
from .errors import StelladdonError, ObjectAlreadyExists, TableNotFound


__all__ = [
    "StellaMongo", "Database", "Table"
]



class StellaMongo:
    """A MongoDB client wich stores the databases with their typed tables."""
    client: MongoClient | None
    """The pymongo.MongoClient instance used by the client."""
    cached_databases: list["Database"]
    """The databases stuctures that have been cached by the client. Should not be used directly."""

    def __init__(self, host: str | None, port: int | None = None) -> None:
        """Create a StellaMongo client. You can set host to None is you want to setup pymongo.MongoClient later manually."""
        if host is None:
            self.client = None
        else:
            self.client = MongoClient(host, port)
        self.cached_databases: list[Database] = []


    def get_database(self, name: str) -> "Database":
        """Get a database from the client."""
        for db in self.cached_databases:
            if db.name == name:
                return db

        db = Database(self, name)
        self.cached_databases.append(db)
        return db


    def __getitem__(self, name: str) -> "Database":
        return self.get_database(name)



class Database:
    """Represent a database that contains the tables."""
    client: StellaMongo
    """The StellaMongo client that is used to connect to the database."""
    name: str
    """The name of the database."""
    tables: list["Table"]
    """The tables that have been registred in the code (not all the existing tables)."""

    def __init__(self, client: StellaMongo, name: str) -> None:
        """Create a database object. Should not be used directly."""
        self.client = client
        self.name = name
        self.tables: list[Table] = []


    def __repr__(self) -> str:
        return f"Database({self.name!r})"


    def __getitem__(self, name: str) -> "Table":
        return self.get_table(name)


    def get_table(self, name: str) -> "Table":
        """Get a table from the database by its name."""
        for table in self.tables:
            if table.collection == name:
                return table

        raise TableNotFound((
            "The table {!r} is not registered in the database {!r}.\n"
            "You should use the .add_table() method to register the table before trying to get it."
        ).format(name, self.name))


    def add_table(self, table: "Table[TableModelT]") -> "Table[TableModelT]":
        """Add a table to the database."""
        self.tables.append(table)
        return table
    

    def create_table(self,
                     model: Type[TableModelT],
                     collection: str,
                     primary_key: str) -> "Table[TableModelT]":
        table = Table(model, collection, self, primary_key)
        self.add_table(table)
        return table


    def table(self,
              collection: str,
              primary_key: str = "_id") -> Callable[[Type[TableModelT]], "Type[TableModelT]"]:
        """Decorator to add a table to the database."""
        def decorator(model: Type[TableModelT]) -> Type[TableModelT]:
            self.add_table(Table(model, collection, self, primary_key))
            return model
        return decorator



class Table(Generic[TableModelT]):
    """A table in a database with an associated model."""
    model: Type[TableModelT]
    """The Pydantic model which validate the objects in the table."""
    collection: str
    """The name of the MongoDB database collection."""
    database: "Database"
    """The database that the table is rattached to."""
    primary_key: str
    """The primary key of all the objects in the table that is used to identify them."""

    def __init__(self,
                 model: Type[TableModelT],
                 collection: str,
                 database: "Database",
                 primary_key: str = "_id") -> None:
        """Create a table object."""
        self.model = model
        self.collection = collection
        self.database = database
        self.primary_key = primary_key


    def __getitem__(self, id: Any) -> TableModelT | None:
        return self.get(id)


    def __repr__(self) -> str:
        return f"Table({self.collection!r} model={self.model.__class__.__name__})"


    def load_object(self, data: dict) -> TableModelT:
        """Load a document from the database (or not) into the table model."""
        return self.model.model_validate(data)


    def get_id_of(self, object: TableModelT) -> Any:
        """Get the primary key of the given object."""
        return getattr(object, self.primary_key)


    def find(self,
             query: dict,
             limit: int | None = None,
             **kwargs) -> list[TableModelT]:
        """Find objects in the table that match the query."""
        cursor = self._collection.find(query, limit=limit if limit is not None else 0, **kwargs)
        return [self.load_object(doc) for doc in cursor]


    def find_one(self,
                 query: dict,
                 **kwargs) -> TableModelT | None:
        """Find one object in the table that match the query."""
        data = self._collection.find_one(query, **kwargs)
        if data is None:
            return None
        return self.load_object(data)


    def get(self, id: Any) -> TableModelT | None:
        """Get an object from the table by its primary key."""
        data = self._collection.find_one({self.primary_key: id})
        if data is None:
            return None
        return self.load_object(data)


    def insert(self, object: TableModelT, comment: str | None = None) -> None:
        """Insert an object in the table."""
        exists = self.get(self.get_id_of(object))
        if exists is not None:
            raise ObjectAlreadyExists((
                "The object you tried to insert in {} already exists in the table.\n"
                "Prefer using .push() method that update the object if it already exists instead of .insert().\n\n"
                "Object you tried to insert:\n{}".format(_pretty(self), _pretty(object))
            ))
        self._collection.insert_one(object.model_dump(), comment=comment)


    def insert_many_iter(self, objects: list[TableModelT], comment: str | None = None) -> None:
        """Insert multiple objects in the table. (Iterative version)"""
        for object in objects:
            self.insert(object, comment=comment)


    def update_many(self, filter: dict, update: dict, comment: str | None = None) -> None:
        """Update objects in the table that are mathing the filter."""
        self._collection.update_many(filter, update, comment=comment)


    def remove_many(self, filter: dict, comment: str | None = None) -> None:
        """Remove objects from the table that are mathing the filter."""
        self._collection.delete_many(filter, comment=comment)


    def update(self, object_or_id: TableModelT | Any, update: dict, comment: str | None = None) -> None:
        """Update an object in the table by its primary key."""
        object_id = object_or_id if (not isinstance(object_or_id, self.model)) \
            else self.get_id_of(object_or_id)
        self._collection.update_one({self.primary_key: object_id}, update, comment=comment)


    def remove(self, object_or_id: TableModelT | Any, comment: str | None = None) -> None:
        """Remove an object from the table by its primary key."""
        object_id = object_or_id if (not isinstance(object_or_id, self.model)) \
            else self.get_id_of(object_or_id)
        self._collection.delete_one({self.primary_key: object_id}, comment=comment)


    def push(self, object: TableModelT, comment: str | None = None) -> None:
        """Insert or update an object in the table depending if it already exists."""
        object_id = self.get_id_of(object)
        exists = self.get(object_id)

        if exists is None:
            self.insert(object, comment)
        else:
            # remove then insert
            self.remove_many({self.primary_key: object_id}, comment)
            self.insert(object, comment)


    @property
    def _collection(self):
        _pymongo_client = self.database.client.client
        if not _pymongo_client:
            raise StelladdonError("The database client is not connected to a MongoDB server.")
        return _pymongo_client[self.database.name][self.collection]
