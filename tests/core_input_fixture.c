/* A core-event-only application: no GTK, XI2, or accessibility provider. */
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    Display *d=XOpenDisplay(NULL); if (!d) return 3;
    Window w=XCreateSimpleWindow(d,DefaultRootWindow(d),40,80,360,240,0,0,0xffffff);
    XStoreName(d,w,"Luda core fallback oracle");
    XClassHint hint={"luda-core-fixture","LudaCoreFixture"}; XSetClassHint(d,w,&hint);
    unsigned long pid=getpid();
    XChangeProperty(d,w,XInternAtom(d,"_NET_WM_PID",False),XA_CARDINAL,32,PropModeReplace,(unsigned char *)&pid,1);
    XSelectInput(d,w,KeyPressMask|ButtonPressMask|ButtonReleaseMask|ExposureMask);
    XMapWindow(d,w);XFlush(d);
    int clicks=0,releases=0,keys=0; char text[128]={0};
    char temporary[4096];snprintf(temporary,sizeof temporary,"%s.tmp",argv[1]);
    for (;;) {
        XEvent event; XNextEvent(d,&event);
        if (event.type==ButtonPress && event.xbutton.button==1) clicks++;
        if (event.type==ButtonRelease && event.xbutton.button==1) releases++;
        if (event.type==KeyPress) {
            char value[8];KeySym symbol;int n=XLookupString(&event.xkey,value,sizeof value,&symbol,NULL);
            if(n==1 && keys<126) text[keys++]=value[0];
        }
        FILE *f=fopen(temporary,"w");if(!f)return 4;
        fprintf(f,"{\"clicks\":%d,\"releases\":%d,\"text\":\"%s\"}\n",clicks,releases,text);
        fclose(f);rename(temporary,argv[1]);
    }
}
