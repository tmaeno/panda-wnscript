#include <time.h>
#include <dlfcn.h> 
#include <ctype.h> 
#include <stdio.h> 
#include <stdlib.h> 
#include <string.h>
#include <stdarg.h>
#include <unistd.h>
#include <libgen.h>
#include <arpa/inet.h>
#include <sys/time.h>  
#include <sys/types.h>  
#include <sys/socket.h>
#include <netinet/in.h> 

#include "outfilename.h"

// put logging message
void pandatracer_putlog(const char *message, const int loglevel)
{
  FILE *fp;
  struct timeval timer;
  struct tm *gt;
  size_t iLen;
  size_t oLen;
  const size_t maxBufSize = 1024;
  char sbuffer[maxBufSize];
  // get current time
  gettimeofday(&timer,NULL);
  gt = gmtime(&(timer.tv_sec));
  // make message
  iLen = strftime(sbuffer,maxBufSize,"%Y-%m-%d %H:%M:%S",gt);
  iLen += snprintf(sbuffer+iLen,maxBufSize-iLen,".%06ld : ",timer.tv_usec);
  switch (loglevel)
    {
    case 1: 
      iLen += snprintf(sbuffer+iLen,maxBufSize-iLen,"WARNING ");
      break;
    case 2:
      iLen += snprintf(sbuffer+iLen,maxBufSize-iLen,"ERROR   ");
      break;
    default:
      iLen += snprintf(sbuffer+iLen,maxBufSize-iLen,"INFO    ");
      break;
    }
  // add message
  strncpy(sbuffer+iLen,message,maxBufSize-iLen);
  iLen = strlen(sbuffer);
  if (iLen > maxBufSize)
    {
      iLen = maxBufSize;
    }
  // get PID
  size_t tmpIdx; 
  pid_t pid = getpid();
  char procbuff[maxBufSize];
  char procmbuff[maxBufSize];
  snprintf(procbuff,sizeof(procbuff)/sizeof(char),"/proc/%d/cmdline",pid); 
  fp = fopen(procbuff,"r");
  if (fp == NULL)
    {
      // proc file not found
      snprintf(procmbuff,sizeof(procmbuff)/sizeof(char),"  cmd: PID=%d",pid);
      strncpy(sbuffer+iLen,procmbuff,maxBufSize-iLen);
      iLen = strlen(sbuffer);
      if (iLen > maxBufSize)
	{
	  iLen = maxBufSize;
	}
    }
  else
    {
      strncpy(sbuffer+iLen,"  cmd: ",maxBufSize-iLen);
      iLen = strlen(sbuffer);
      if (iLen > maxBufSize)
	{
	  iLen = maxBufSize;
	}
      // read cmdline from proc file
      fread(procbuff,sizeof(char),sizeof(procbuff)/sizeof(char),fp);
      // close
      fclose(fp);
      // remove un-printable chars
      for (tmpIdx=0;tmpIdx<strlen(procbuff);tmpIdx++)
	{
	  if (!isprint(procbuff[tmpIdx]))
	    {
	      // set \0 to extract only exe name
	      procbuff[tmpIdx] = '\0';
	      break;
	    }
	}
      // add exe name
      strncpy(sbuffer+iLen,basename(procbuff),maxBufSize-iLen);
      if (strlen(basename(procbuff)) > maxBufSize-iLen)
	{
	  sbuffer[maxBufSize-1] = '\0';
	}
      iLen = strlen(sbuffer);
      if (iLen > maxBufSize)
	{
	  iLen = maxBufSize;
	}
    }
  // add newline+delimiter
  strncpy(sbuffer+iLen,"\n\0",maxBufSize-iLen);
  iLen = strlen(sbuffer);
  // delimiter just in case
  sbuffer[maxBufSize-2] = '\n';  
  sbuffer[maxBufSize-1] = '\0';
  // open file
  fp = fopen(pandatracer_outfilename,"a");
  if (fp == NULL)
    {
      perror("cannot open PandaTracer logfile"); 
      exit(2);
    }
  // write
  oLen = fwrite(sbuffer,sizeof(char),iLen,fp);
  if (oLen != iLen)
    {
      perror("cannot put all logging message");
      exit(2);
    }
  // close
  fclose(fp);
  return;
}


  
int connect(int socket, const struct sockaddr *serv_addr, socklen_t addrlen)
{ 
  struct sockaddr_in *addrv4 = (struct sockaddr_in *)serv_addr;
  char subffer[512];
  char ipaddr[INET_ADDRSTRLEN]; 
  inet_ntop(AF_INET,&(addrv4->sin_addr),ipaddr,sizeof ipaddr); 
  uint16_t iport;
  iport = ntohs(addrv4->sin_port);
  if (iport != 53) 
    {
      snprintf(subffer,sizeof(subffer)/sizeof(char),"connect: %s:%u",
	       ipaddr,iport);
      pandatracer_putlog(subffer,0);
    }
  typedef int (*FP_orig)(int,const struct sockaddr *,socklen_t); 
  FP_orig org_call = dlsym(((void *) -1l), "connect"); 
  return org_call(socket,serv_addr,addrlen); 
} 


int execve(const char *filename, char *const argv[],
	   char *const envp[])
{
  int ret;
  int ldFound = -1;
  int pandaFound = -1;
  char subffer[512];
  char ldbffer[4096];
  unsigned long iLoop;
  const char * ld_preload    = "LD_PRELOAD=";
  const char * panda_preload = "PANDA_PRELOAD=";
  // loop over all env vars
  for (iLoop=0; envp[iLoop] != NULL; iLoop++)
    {
      if (strstr(envp[iLoop],"LD_PRELOAD="))
	{
	  ldFound = iLoop;
	}
      else if (strstr(envp[iLoop],panda_preload))
	{
	  pandaFound = iLoop;
	}
      if ((ldFound >= 0) && (pandaFound >= 0))
	{
	  break;
	}
    }
  // set LD_PRELOAD if not found
  if (ldFound < 0) 
    {
      if (pandaFound < 0)
	{
	  // either LD_PRELOAD or PANDA_LD_PRELOAD not found
	  snprintf(subffer,sizeof(subffer)/sizeof(char),"evecve: %s  no PANDA/LD_PRELOAD",
		   basename((char *)filename));
	  pandatracer_putlog(subffer,2);
	}
      else
	{
	  size_t iLen;
	  // add LD_PRELOAD=
	  strncpy(ldbffer,ld_preload,strlen(ld_preload));
	  iLen = strlen(ldbffer);
	  // copy PANDA_PRELOAD
	  strncpy(ldbffer+iLen,envp[pandaFound]+strlen(panda_preload),sizeof(ldbffer)-iLen);
	  iLen += strlen(envp[pandaFound])-strlen(panda_preload);
	  if (iLen >= sizeof(ldbffer))
	    {
	      // too long
	      snprintf(subffer,sizeof(subffer)/sizeof(char),"evecve: %s  too long PANDA_PRELOAD",
		       basename((char *)filename));
	      pandatracer_putlog(subffer,2);
	    }
	  else
	    {
	      // add delimiter
	      ldbffer[iLen] = '\0';
	      // copy to PANDA_PRELOAD's string
	      strncpy(envp[pandaFound],ldbffer,strlen(ldbffer));
	      envp[pandaFound][strlen(ldbffer)] = '\0';
	      snprintf(subffer,sizeof(subffer)/sizeof(char),"evecve: %s  new %s",
		       basename((char *)filename),envp[pandaFound]);
	      pandatracer_putlog(subffer,0);
	    }
	}
    }
  else
    // check LD_PRELOAD
    {
      // wrapper is not found in LD_PRELOAD
      if (strstr(envp[ldFound],pandatracer_sofilename) == NULL)
	{
	  snprintf(subffer,sizeof(subffer)/sizeof(char),"evecve: %s  wrapper=%s is not in LD_PRELOAD=%s",
                   basename((char *)filename),pandatracer_sofilename,envp[ldFound]);
	  pandatracer_putlog(subffer,2);
	}
    }
  typedef int (*FP_orig)(const char *,char *const [], char *const []);
  FP_orig org_call = dlsym(((void *) -1l),"execve"); 
  ret = org_call(filename,argv,envp); 
  return ret;
}
  
