$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class ThaiMenuD3DProbe {
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr LoadLibraryW(string path);
 [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern bool SetDllDirectoryW(string path);
 [DllImport("kernel32.dll")] static extern uint SetErrorMode(uint mode);
 [DllImport("dxgi.dll")] static extern int CreateDXGIFactory2(uint flags,ref Guid iid,out IntPtr factory);
 [DllImport("d3d12.dll")] static extern int D3D12CreateDevice(IntPtr adapter,uint level,ref Guid iid,out IntPtr device);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate IntPtr Create(uint sdk);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate IntPtr CreateOn12(uint sdk,IntPtr overrides,uint count);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate uint Count(IntPtr self);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Identifier(IntPtr self,uint adapter,uint flags,IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Caps(IntPtr self,uint adapter,uint device,IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Mode(IntPtr self,uint adapter,IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int EnumWarp(IntPtr self,ref Guid iid,out IntPtr adapter);
 static Delegate Method(IntPtr self,int slot,Type type) {return Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(Marshal.ReadIntPtr(self),slot*IntPtr.Size),type);}
 public static void Run(string root) {
  SetErrorMode(0x8003);SetDllDirectoryW(root);
  IntPtr lib=LoadLibraryW(root+"\\d3d8.dll");Console.WriteLine("DLL="+lib+" error="+Marshal.GetLastWin32Error());
  if(lib==IntPtr.Zero)return;
  Create create=(Create)Marshal.GetDelegateForFunctionPointer(GetProcAddress(lib,"Direct3DCreate8"),typeof(Create));
  IntPtr api=create(220);Console.WriteLine("Direct3DCreate8="+api);if(api==IntPtr.Zero)return;
  uint count=((Count)Method(api,4,typeof(Count)))(api);Console.WriteLine("Adapters="+count);
  IntPtr data=Marshal.AllocHGlobal(4096);
  try {
   for(uint i=0;i<count;i++) {
    int hr=((Identifier)Method(api,5,typeof(Identifier)))(api,i,2,data);
    Console.WriteLine("Identifier hr="+hr.ToString("X8")+" driver="+Marshal.PtrToStringAnsi(data)+" description="+Marshal.PtrToStringAnsi(IntPtr.Add(data,512)));
    hr=((Mode)Method(api,8,typeof(Mode)))(api,i,data);Console.WriteLine("DisplayMode hr="+hr.ToString("X8")+" width="+Marshal.ReadInt32(data)+" height="+Marshal.ReadInt32(data,4)+" format="+Marshal.ReadInt32(data,12));
    hr=((Caps)Method(api,13,typeof(Caps)))(api,i,1,data);Console.WriteLine("HAL caps hr="+hr.ToString("X8"));
   }
  } finally {Marshal.FreeHGlobal(data);}
 }
 public static void RunOn12(bool warp) {
  SetErrorMode(0x8003);
  IntPtr lib=LoadLibraryW(Environment.GetFolderPath(Environment.SpecialFolder.System)+"\\d3d9.dll");
  IntPtr args=Marshal.AllocHGlobal(24);
  for(int i=0;i<24;i++)Marshal.WriteByte(args,i,0);
  Marshal.WriteInt32(args,1);
  if(warp) {
   IntPtr factory,adapter,device;
   Guid factoryIid=new Guid("1bc6ea02-ef36-464f-bf0c-21ca39e5168a");
   Guid adapterIid=new Guid("2411e7e1-12ac-4ccf-bd14-9798e8534dc0");
   Guid deviceIid=new Guid("189819f1-1db6-4b57-be54-1821339b85f7");
   int hr=CreateDXGIFactory2(0,ref factoryIid,out factory);Console.WriteLine("DXGI factory="+hr.ToString("X8"));if(hr<0)return;
   hr=((EnumWarp)Method(factory,27,typeof(EnumWarp)))(factory,ref adapterIid,out adapter);Console.WriteLine("WARP adapter="+hr.ToString("X8"));if(hr<0)return;
   hr=D3D12CreateDevice(adapter,0xb000,ref deviceIid,out device);Console.WriteLine("WARP device="+hr.ToString("X8"));if(hr<0)return;
   Marshal.WriteIntPtr(args,4,device);
  }
  CreateOn12 create=(CreateOn12)Marshal.GetDelegateForFunctionPointer(GetProcAddress(lib,"Direct3DCreate9On12"),typeof(CreateOn12));
  IntPtr api=create(32,args,1);Marshal.FreeHGlobal(args);
  Console.WriteLine("Direct3DCreate9On12="+api);if(api==IntPtr.Zero)return;
  IntPtr data=Marshal.AllocHGlobal(4096);
  try {
   uint count=((Count)Method(api,4,typeof(Count)))(api);Console.WriteLine("On12 adapters="+count);
   int hr=((Caps)Method(api,14,typeof(Caps)))(api,0,1,data);Console.WriteLine("On12 HAL caps hr="+hr.ToString("X8"));
  } finally {Marshal.FreeHGlobal(data);}
 }
}
'@
[ThaiMenuD3DProbe]::Run($taskRoot)
[ThaiMenuD3DProbe]::RunOn12($false)
[ThaiMenuD3DProbe]::RunOn12($true)
