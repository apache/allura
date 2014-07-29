//1) Copy to the new collection with data updates
db.email_address.find().snapshot().forEach(function(e){
    e.email = e._id;
    e._id = new ObjectId();
    db.email_address_new.insert(e);
    db.email_address.update({'_id': e._id}, {'migrated': true})
});
//2) Updated code on production(git pull)
//3) Rename collections
db.email_address.renameCollection("email_address_old", {dropTarget: true})
db.email_address_new.renameCollection("email_address", {dropTarget: true})
//4) Post Migration - copy/update all the object which were created between 1)&2)
db.email_address_old.find({'migrated': {'$not': false}}).snapshot().forEach(function(e){
    e.email = e._id;
    e._id = new ObjectId();
    db.email_address.insert(e);
    db.email_address_old.update({'_id': e._id}, {'migrated': true})
});

db.email_address_old.drop()
