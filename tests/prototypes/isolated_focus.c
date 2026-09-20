#include <X11/Xlib.h>
#include <X11/keysym.h>
#include <X11/extensions/XInput2.h>
#include <X11/extensions/XTest.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv){
 Display*d=XOpenDisplay(NULL);if(!d)return 2;
 int major=2,minor=0;XIQueryVersion(d,&major,&minor);
 if(!strcmp(argv[1],"add")){XIAddMasterInfo a={XIAddMaster,"luda-probe",getenv("LUDA_CORE_EVENTS")!=NULL,True};XIChangeHierarchy(d,(XIAnyHierarchyChangeInfo*)&a,1);XSync(d,False);return 0;}
 int n,mp=0,mk=0,sp=0,sk=0;XIDeviceInfo*ds=XIQueryDevice(d,XIAllDevices,&n);
 for(int i=0;i<n;i++)if(strstr(ds[i].name,"luda-probe")){if(ds[i].use==XIMasterPointer)mp=ds[i].deviceid;if(ds[i].use==XIMasterKeyboard)mk=ds[i].deviceid;if(ds[i].use==XISlavePointer)sp=ds[i].deviceid;if(ds[i].use==XISlaveKeyboard)sk=ds[i].deviceid;}
 XIFreeDeviceInfo(ds);if(!mp)return 3;
 if(!strcmp(argv[1],"remove")){XIRemoveMasterInfo a={XIRemoveMaster,mp,XIAttachToMaster,2,3};XIChangeHierarchy(d,(XIAnyHierarchyChangeInfo*)&a,1);}
 if(!strcmp(argv[1],"click")){XIWarpPointer(d,mp,None,DefaultRootWindow(d),0,0,0,0,atoi(argv[2]),atoi(argv[3]));XSync(d,False);XDevice*p=XOpenDevice(d,sp);XTestFakeDeviceButtonEvent(d,p,atoi(argv[4]),True,NULL,0,0);XTestFakeDeviceButtonEvent(d,p,atoi(argv[4]),False,NULL,0,0);XCloseDevice(d,p);}
 if(!strcmp(argv[1],"type")){XISetFocus(d,mk,strtoul(argv[2],NULL,0),CurrentTime);XDevice*k=XOpenDevice(d,sk);int key=XKeysymToKeycode(d,argc>3?XStringToKeysym(argv[3]):XK_a);XTestFakeDeviceKeyEvent(d,k,key,True,NULL,0,0);XTestFakeDeviceKeyEvent(d,k,key,False,NULL,0,0);XCloseDevice(d,k);}
 XSync(d,False);XCloseDisplay(d);return 0;
}
