import os
import base64
import pymysql
import ftplib
import hashlib
import math

globalPercentage = -1


def log(msg, status=200):
    if status == 200:
        print(msg)
    elif status == 400:
        print('Fatal error: ', msg)
        exit()


def splitConfig(value):
    if ' && ' in value:
        return value.split(' && ')
    else:
        return [value]


def getConfig(configFile, passFile):
    if not os.path.isfile(configFile) and os.path.isfile(passFile):
        print('Config file or password file not found.', configFile, passFile)
        exit()

    with open(configFile, "r") as content:
        content = content.read().split('\n')
        content = [i.split(' = ') for i in content]
        for i in content:
            if i[0] == 'ip':
                ip = i[1]
            elif i[0] == 'backUpDirectory':
                whereArr = splitConfig(i[1])
            elif i[0] == 'piBackUpDirectory':
                ftppreArr = splitConfig(i[1])
            elif i[0] == 'piDeleteDirectory':
                ftptrash = i[1]
            elif i[0] == 'excludeDirectorys':
                excludeDirs = splitConfig(i[1])
            elif i[0] == 'excludeFiles':
                excludeFiles = splitConfig(i[1])
            elif i[0] == 'realTimeUpdates':
                realTimeUpdates = i[1] == 'True'

    with open(passFile, "r") as content:
        passwd = base64.b64decode(content.read().rstrip()).decode('UTF-8')

    return ip, whereArr, ftppreArr, ftptrash, excludeDirs, excludeFiles, realTimeUpdates, passwd


def FTPConnect(ip, passwd, user='pi'):
    try:
        return ftplib.FTP(ip, user, passwd)
    except Exception as e:
        log(e, 400)


def DBConnect(ip, passwd, user='phpmyadmin', db='BACKUP'):
    try:
        return pymysql.connect(ip, user, passwd, db)
    except Exception as e:
        log(e, 400)


def getAmountFiles(directory, excludeDirs, excludeFiles, amount=0):
    try:
        content = os.listdir(directory)
    except Exception as e:
        return 0
    for element in content:
        path = directory + element
        if path in excludeDirs or path in excludeFiles:
            continue
        if os.path.isdir(path):
            amount += getAmountFiles(path + '/', excludeDirs, excludeFiles)
        else:
            amount += 1
    return amount


def updateProgressBar(Percentage=0, description='', realTimeUpdates=False):
    global globalPercentage
    Percentage = math.floor(Percentage)
    if not realTimeUpdates and not Percentage == globalPercentage:
        globalPercentage = Percentage
    elif not realTimeUpdates:
        return
    if len(description) > 60:
        description = description[:57] + '...'
    else:
        description += ' ' * (60 - len(description))
    GPercentage = math.floor(Percentage / 2)
    graphicPercentage = ' [%s] ' % ('#' * GPercentage + ' ' * (50 - GPercentage))
    print(' ' + str(Percentage) + '%' + graphicPercentage + description, end="\r")


def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest().upper()


def parseTilde(ruta):
    ruta = ruta.replace('º', 'Â°').replace('ª', 'Âª').replace('á', 'Ã¡')
    ruta = ruta.replace('é', 'Ã©').replace('í', 'Ã­').replace('ó', 'Ã³')
    ruta = ruta.replace('ú', 'Ãº').replace('Á', 'Ã¡').replace('É', 'Ã©')
    ruta = ruta.replace('Í', 'Ã­').replace('Ó', 'Ã³').replace('Ú', 'Ãº')
    ruta = ruta.replace('ß', 'ss').replace('ö', 'o')
    return ruta


def calculateDiferences(directory, created, modified, unchanged, dbdata, excludeDirs, excludeFiles, realTimeUpdates, total, count=0):
    try:
        content = os.listdir(directory)
    except Exception as e:
        return count
    for element in content:
        path = directory + element
        if path in excludeDirs or path in excludeFiles:
            continue
        if os.path.isdir(path):
            count = calculateDiferences(path + '/', created, modified, unchanged, dbdata, excludeDirs, excludeFiles, realTimeUpdates, total, count)
        else:
            count += 1
            try:
                hashmd5 = md5(path)
            except Exception as e:
                continue
            DBpath = parseTilde(path)
            if DBpath in dbdata.keys():
                if hashmd5 == dbdata[DBpath]:
                    unchanged[DBpath] = hashmd5
                else:
                    modified[path] = hashmd5
                del dbdata[DBpath]
            else:
                created[path] = hashmd5
            updateProgressBar(count * 100 / total, path, realTimeUpdates)
    return count


def mkdRecursive(ftp, path):
    pathParts = path.split('/')
    completePath = ''
    for part in pathParts:
        completePath += '/' + part
        try:
            ftp.mkd(completePath.lstrip('/'))
        except Exception:
            pass


def ftpUpload(ftp, path, ftppreArr, whereArr):
    serverLocation = ''
    for idx, localPath in enumerate(whereArr):
        if localPath in path:
            serverLocation = parseTilde(path.replace(localPath, ftppreArr[idx]))
            break
    mkdRecursive(ftp, serverLocation.replace(serverLocation.split('/')[-1], '').rstrip('/'))
    try:
        with open(path, 'rb') as upload:
            ftp.storbinary('STOR ' + serverLocation, upload)
        return True
    except Exception as e:
        log(e)
        return False


def ftpDelete(ftp, path, ftppreArr, whereArr, ftptrash):
    serverLocation = ''
    for idx, localPath in enumerate(whereArr):
        if localPath in path:
            serverLocation = path.replace(localPath, parseTilde(ftppreArr[idx]))
            serverTrash = path.replace(localPath, parseTilde(ftptrash))
            break
    mkdRecursive(ftp, serverTrash.replace(serverTrash.split('/')[-1], '').rstrip('/'))
    try:
        ftp.rename(serverLocation, serverTrash)
        container = serverLocation.replace(serverLocation.split('/')[-1], '').rstrip('/')
        dirList = ftp.nlst(container)
        if not dirList:
            ftp.rmd(container)
        return True
    except Exception as e:
        log(e)
        return False


def dbUpdate(db, path, md5, action):
    if not action == 'delete':
        path = parseTilde(path)
    path = path.replace('\'', '\\\'')
    cursor = db.cursor()
    if action == 'create':
        sql = "INSERT INTO REFERENCESR(PATH, HASH) VALUES ('" + path + "', '" + md5 + "')"
    elif action == 'update':
        sql = 'UPDATE REFERENCESR SET HASH = \'' + md5 + '\' WHERE PATH = \'' + path + '\''
    elif action == 'delete':
        sql = 'DELETE FROM REFERENCESR WHERE PATH = \'' + path + '\''
    try:
        cursor.execute(sql)
        db.commit()
    except Exception as e:
        log(e)
        db.rollback()
