import sqlalchemy

site_meta = sqlalchemy.MetaData()
mail_meta = sqlalchemy.MetaData()
task_meta = sqlalchemy.MetaData()
epic_meta = sqlalchemy.MetaData()

class Empty(object):pass
tables = Empty()
