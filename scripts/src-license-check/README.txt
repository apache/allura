This is Apache Ant buildfile that can be used to do an automated license audit
of the local Allura codebase. To use it, you need to:

1. Install Apache Ant, version 1.8.0 or later. Apache Ant is very popular
software package and there are good chances it is already available in your
operating system's software repository. System-independent binary files are
available from http://ant.apache.org/bindownload.cgi in case you need them.

Be advised that Apache Ant requires Java Virtual Machine to work. For futher
details, head to http://ant.apache.org/.

2. Download and unpack Apache Rat. Apache Rat is a release audit tool (hence
the name) used by Apache Software Foundation projects. It can be obtained from
http://creadur.apache.org/rat/download_rat.cgi  After unpacking downloaded zip
or tarball, you should have a directory with several .jar files and a lib/
directory.

3. Make this directory with the Ant buildfile (build.xml file) your working directory.
Then execute `ant -lib [path to Apache Rat lib/ directory]`, for example:

ant -lib ../../../apache-rat-0.11

The buildfile will be parsed by Apache Ant and after a couple of seconds, you
should be presented with a file list along with potential licensing issues.

You should run this on a clean checkout / release of Allura, to avoid reporting
on local files.