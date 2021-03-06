-- $Header: /tmp/libdirac/tmp.stZoy15380/dirac/DIRAC3/DIRAC/WorkloadManagementSystem/DB/SandboxDB.sql,v 1.7 2009/08/26 09:39:53 rgracian Exp $

-- ------------------------------------------------------------------------------
--
--  Schema definition for the SandboxDB database - containing the job status
--  history ( logging ) information
-- -
-- ------------------------------------------------------------------------------

DROP DATABASE IF EXISTS SandboxDB;

CREATE DATABASE SandboxDB;

-- ------------------------------------------------------------------------------
-- Database owner definition

USE mysql;
DELETE FROM user WHERE user='Dirac';

--
-- Must set passwords for database user by replacing "must_be_set".
--

GRANT SELECT,INSERT,LOCK TABLES,UPDATE,DELETE,CREATE,DROP,ALTER ON SandboxDB.* TO Dirac@localhost IDENTIFIED BY 'must_be_set';
GRANT SELECT,INSERT,LOCK TABLES,UPDATE,DELETE,CREATE,DROP,ALTER ON SandboxDB.* TO Dirac@'%' IDENTIFIED BY 'must_be_set';

FLUSH PRIVILEGES;

-- -----------------------------------------------------------------------------
USE SandboxDB;

-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS InputSandbox;
CREATE TABLE InputSandbox (
    JobID INTEGER NOT NULL,
    FileName VARCHAR(255) NOT NULL,
    FileBody LONGBLOB NOT NULL,
    FileLink VARCHAR(255),
    FileSize int(11) NOT NULL default '0',
    Partition varchar(32),
    UploadDate DATETIME,
    RetrieveDate DATETIME,
    PRIMARY KEY (JobID,FileName)
) TYPE=MyISAM MAX_ROWS=150000 AVG_ROW_LENGTH=150000;

-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS OutputSandbox;
CREATE TABLE OutputSandbox (
    JobID INTEGER NOT NULL,
    FileName VARCHAR(255) NOT NULL,
    FileBody LONGBLOB NOT NULL,
    FileLink VARCHAR(255),
    FileSize int(11) NOT NULL default '0',
    Partition varchar(32),
    UploadDate DATETIME,
    RetrieveDate DATETIME,
    PRIMARY KEY (JobID,FileName)
) TYPE=MyISAM MAX_ROWS=150000 AVG_ROW_LENGTH=150000;

-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS OutputSandboxPartitions;
CREATE TABLE OutputSandboxPartitions (
    PartID INTEGER NOT NULL AUTO_INCREMENT,
    CreationDate DATETIME,
    LastUpdate DATETIME,
    DataSize BIGINT NOT NULL DEFAULT 0,
    TableSize BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (PartID)
);

-- ------------------------------------------------------------------------------
DROP TABLE IF EXISTS InputSandboxPartitions;
CREATE TABLE InputSandboxPartitions (
    PartID INTEGER NOT NULL AUTO_INCREMENT,
    CreationDate DATETIME,
    LastUpdate DATETIME,
    DataSize BIGINT NOT NULL DEFAULT 0,
    TableSize BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (PartID)
);