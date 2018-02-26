import backuptools as bkt

print('Starting up...')

dbdata = {}
ip, whereArr, ftppreArr, ftptrash, excludeDirs, excludeFiles, realTimeUpdates, passwd = bkt.getConfig("./backup.config", "./db.pass")
print('You are about to BackUp from', whereArr, 'to', ip, ':', ftppreArr, 'excluding', excludeDirs, excludeFiles, 'and recycle bin', ftptrash)

db = bkt.DBConnect(ip, passwd)
cursor = db.cursor()
cursor.execute("SELECT * FROM REFERENCESR")
rows = cursor.fetchall()
db.close()
for row in rows:
    dbdata[row[0]] = row[1]
print(len(dbdata), 'files found on previus BackUp. Calculating changes...')

total = 0
for directory in whereArr:
    total += bkt.getAmountFiles(directory, excludeDirs, excludeFiles)

created, modified, unchanged = ({} for i in range(3))

bkt.updateProgressBar()
count = 0
for directory in whereArr:
    count = bkt.calculateDiferences(directory, created, modified, unchanged, dbdata, excludeDirs, excludeFiles, realTimeUpdates, total, count)


print('\nThe next changes will be aplied to the BackUp version: ')
print(len(created), 'files will be created.')
print(len(modified), 'files will be modified.')
print(len(dbdata), 'files will be moved to the recycle bin.')
print(len(unchanged), 'files will remain unchanged.')

ftp = bkt.FTPConnect(ip, passwd)
db = bkt.DBConnect(ip, passwd)

i = 0
todoLen = len(created)
bkt.updateProgressBar(realTimeUpdates=True)
for path, md5 in created.items():
    bkt.updateProgressBar(100 * i / todoLen, 'Uploading ' + path, True)
    i += 1
    if bkt.ftpUpload(ftp, path, ftppreArr, whereArr):
        bkt.dbUpdate(db, path, md5, 'create')

i = 0
todoLen = len(modified)
bkt.updateProgressBar(realTimeUpdates=True)
for path, md5 in modified.items():
    bkt.updateProgressBar(100 * i / todoLen, 'Modifiying ' + path, True)
    i += 1
    if bkt.ftpUpload(ftp, path, ftppreArr, whereArr):
        bkt.dbUpdate(db, path, md5, 'update')

i = 0
todoLen = len(dbdata)
bkt.updateProgressBar(realTimeUpdates=True)
for path, md5 in dbdata.items():
    bkt.updateProgressBar(100 * i / todoLen, 'Moving to Trash ' + path, True)
    i += 1
    if bkt.ftpDelete(ftp, path, ftppreArr, whereArr, ftptrash):
        bkt.dbUpdate(db, path, md5, 'delete')

ftp.quit()
db.close()
print('\nBackUp completed!')
