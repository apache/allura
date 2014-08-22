db.email_address.renameCollection("email_address_old", {dropTarget: true});
db.email_address_new.renameCollection("email_address", {dropTarget: true});