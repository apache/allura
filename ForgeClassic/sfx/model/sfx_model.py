import sqlalchemy as sa

site_meta = sa.MetaData()
mail_meta = sa.MetaData()
task_meta = sa.MetaData()
epic_meta = sa.MetaData()

class Empty(object):pass
tables = Empty()
