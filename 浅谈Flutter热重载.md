## 前言

这是浅谈 Flutter 系列的第二篇，上一篇是 [浅谈Flutter构建](https://juejin.im/post/5d68fb1af265da03d063b69e)，在上一篇中，主要是理清 Flutter 在 debug 和 release 模式下生成的不同产物分别是什么，怎么调试 build_tools 源码等等，这些不会在后面重复讨论，所以有需要的同学可以先看下第一篇。

热重载是 Flutter 的一个大杀器，非常受欢迎，特别是对于客户端开发的同学来说，项目大了以后，可能就会出现，代码改一行，构建半小时的场面。之前非常火热的组件化方案其实一点就是为了解决构建时间过长的痛点。而对于 Flutter 来说，有两种模式可以快速应用修改：hot reload（热重载）和 hot restart（热重启），其中 hot reload 只需要几百毫秒就可以完成更新，速度非常快，hot restart 稍微慢一点，需要秒单位。在修改了资源文件或需要重新构建状态，只能使用 hot restart。

## 源码解析

在第一篇文章中，我们说到，对于每个 Flutter 命令，都有一个 Command 类与之对应，我们使用的 `flutter run` 是由 RunCommand 类处理的。

### HotRunner

默认在 debug 模式下会开启 hot mode，release 模式下默认关闭，可以在执行 run 命令的时候，添加 `--not-hot` 来禁用 hot mode。

当启用 hot mode 时，会使用 HotRunner 来启动 Flutter 应用。

``` dart
if (hotMode) {                                          
  runner = HotRunner(                                   
    flutterDevices,                                     
    target: targetFile,                                 
    debuggingOptions: _createDebuggingOptions(),        
    benchmarkMode: argResults['benchmark'],             
    applicationBinary: applicationBinaryPath == null    
        ? null                                          
        : fs.file(applicationBinaryPath),               
    projectRootPath: argResults['project-root'],        
    packagesFilePath: globalResults['packages'],        
    dillOutputPath: argResults['output-dill'],          
    saveCompilationTrace: argResults['train'],          
    stayResident: stayResident,                         
    ipv6: ipv6,                                         
  );                                                    
} 
```

hot mode 开启后，首先会进行初始化，这部分相关的代码在 `HotRunner run()`。

* 构建应用，以 Anroid 为例，这里会调用 gradle 去执行 assemble task 来生成 APK 文件

  ``` dart
  if (!prebuiltApplication || androidSdk.licensesAvailable && androidSdk.latestVersion == null) {   
    printTrace('Building APK');                                                                     
    final FlutterProject project = FlutterProject.current();                                        
    await buildApk(                                                                                 
        project: project,                                                                           
        target: mainPath,                                                                           
        androidBuildInfo: AndroidBuildInfo(debuggingOptions.buildInfo,                              
          targetArchs: <AndroidArch>[androidArch]                                                   
        ),                                                                                           
    );                                                                                              
    // Package has been built, so we can get the updated application ID and                         
    // activity name from the .apk.                                                                 
    package = await AndroidApk.fromAndroidProject(project.android);                                 
  }                                                                                                 
  ```

* 构建 APK 成功，则会使用 adb 启动它，并建立 sockets 连接，转发主机的端口到设备上。

  > 这里的主机指的是，运行 Flutter 命令的环境，一般是 PC。设备指的是，运行 Flutter 应用的环境，这里指手机。

  转发端口的意义是为了与设备上 Dart VM（虚拟机）进行通信，这个后面会说到。

  在使用 adb 启动应用后，会监听 log 输出，使用正则表达式去获取 sockets 连接地址后，设置端口转发。

  ``` dart
  void _handleLine(String line) {                                                                                  
    Uri uri;                                                                                                       
    final RegExp r = RegExp('${RegExp.escape(serviceName)} listening on ((http|\/\/)[a-zA-Z0-9:/=_\\-\.\\[\\]]+)');
    final Match match = r.firstMatch(line);                                                                        
                                                                                                                   
    if (match != null) {                                                                                           
      try {                                                                                                        
        uri = Uri.parse(match[1]);                                                                                 
      } catch (error) {                                                                                            
        _stopScrapingLogs();                                                                                       
        _completer.completeError(error);                                                                           
      }                                                                                                            
    }                                                                                                              
                                                                                                                   
    if (uri != null) {                                                                                             
      assert(!_completer.isCompleted);                                                                             
      _stopScrapingLogs();                                                                                         
      _completer.complete(_forwardPort(uri));                                                                      
    }                                                                                                              
                                                                                                                   
  }
  
  // 转发端口
  Future<Uri> _forwardPort(Uri deviceUri) async {                                                         
    printTrace('$serviceName URL on device: $deviceUri');                                                 
    Uri hostUri = deviceUri;                                                                              
                                                                                                          
    if (portForwarder != null) {                                                                          
      final int actualDevicePort = deviceUri.port;                                                        
      final int actualHostPort = await portForwarder.forward(actualDevicePort, hostPort: hostPort);       
      printTrace('Forwarded host port $actualHostPort to device port $actualDevicePort for $serviceName');
      hostUri = deviceUri.replace(port: actualHostPort);                                                  
    }                                                                                                     
                                                                                                          
    assert(InternetAddress(hostUri.host).isLoopback);                                                     
    if (ipv6) {                                                                                           
      hostUri = hostUri.replace(host: InternetAddress.loopbackIPv6.host);                                 
    }                                                                                                     
                                                                                                          
    return hostUri;                                                                                       
  }                                                                                                       
  ```

  在我的设备上，匹配地址如下：

  ``` 
  09-08 14:14:12.708  6122  6149 I flutter : Observatory listening on http://127.0.0.1:45093/6p_NsmXILHw=/
  ```

* 根据第二步建立的 sockets 连接地址和转发的端口，建立 RPC 通信，这里使用的 [json_rpc_2](https://github.com/dart-lang/json_rpc_2) 。

  > 关于 Dart VM 支持的 RPC 方法可以看这里：[Dart VM Service Protocol 3.26][https://github.com/dart-lang/sdk/blob/master/runtime/vm/service/service.md]
  >
  > 关于 JSON-RPC，可以看这里：[JSON-RPC 2.0 Specification](https://www.jsonrpc.org/specification)
  >
  > 注意：Dart VM 只支持 WebSocket，不支持 HTTP。
  >
  > "The VM will start a webserver which services protocol requests via WebSocket. It is possible to make HTTP (non-WebSocket) requests, but this does not allow access to VM *events* and is not documented here."

  ``` dart
  static Future<VMService> connect(                                                                            
    Uri httpUri, {                                                                                             
    ReloadSources reloadSources,                                                                               
    Restart restart,                                                                                           
    CompileExpression compileExpression,                                                                       
    io.CompressionOptions compression = io.CompressionOptions.compressionDefault,                              
  }) async {                                                                                                   
    final Uri wsUri = httpUri.replace(scheme: 'ws', path: fs.path.join(httpUri.path, 'ws'));                   
    final StreamChannel<String> channel = await _openChannel(wsUri, compression: compression);                 
    final rpc.Peer peer = rpc.Peer.withoutJson(jsonDocument.bind(channel), onUnhandledError: _unhandledError); 
    final VMService service = VMService(peer, httpUri, wsUri, reloadSources, restart, compileExpression);      
    // This call is to ensure we are able to establish a connection instead of                                 
    // keeping on trucking and failing farther down the process.                                               
    await service._sendRequest('getVersion', const <String, dynamic>{});                                       
    return service;                                                                                            
  }                                                                                                            
  ```

  

### RunCommand

hot 模式默认在 debug 模式下开启，在 release 模式下关闭，可以使用 `--not-hot` 手动禁用。

当启用 hot 模式时，会使用 HotRunner 来启动应用。

``` dart

```

### HotRunner

这里会做两件事，第一，调用 FlutterDevice.runHot；第二，调用 attach。

#### runHot

`runHot()` 函数的作用是，启动应用，转发设备端口，提供给后面 RPC 通信使用。这一块的逻辑是在 `Device.startApp()` 函数中，Device 是一个抽象类，这里我们用 AndroidDevice 来讲解。

##### build apk

在启动之前，会先判断是否需要重新构建 APK，这里实际是调用的 assemble task 去打包的，完整命令如下：

``` shell
./gradlew -Ptarget main.dart -Ptarget-platform=android-arm64 assembleDebug
```

##### observatory

ProtocolDiscovery 会监听 log 输出，然后将设备端口转发到主机端口，这里是使用正则表达式去匹配对应的日志：

> 比如，手机上启动一个服务，监听手机端口 2222，在 PC 上建立一个连接到主机端口 1111 的 socket，然后使用：
>
> ``` shell
> adb forward tcp:1111 tcp:2222
> ```
>
> 就可以将发送到 PC 端口 1111 的数据转发到手机的 2222 端口上。

``` dart
Uri uri;                                                                                                           
final RegExp r = RegExp('${RegExp.escape(serviceName)} listening on ((http|\/\/)[a-zA-Z0-9:/=_\\-\.\\[\\]]+)');    
final Match match = r.firstMatch(line);                                                                            
```

然后使用 adb 命令转发端口：

``` dart
if (portForwarder != null) {                                                                             
  final int actualDevicePort = deviceUri.port;                                                           
  final int actualHostPort = await portForwarder.forward(actualDevicePort, hostPort: hostPort);          
  printTrace('Forwarded host port $actualHostPort to device port $actualDevicePort for $serviceName');   
  hostUri = deviceUri.replace(port: actualHostPort);                                                     
}                                                                                                        
```

这里转发端口的意义在于，主机（这里指 PC）可以跟设备（这里指手机）上 Dart VM 进行通信，注意，这里是通信是双向的，即主机可以发送信息到设备，设备也可以发送信息到主机。

##### start

最后使用 adb 启动 Activity，返回在第二步生成的 observatoryUri：

``` dart
try {                                                                                
  Uri observatoryUri;                                                                
                                                                                     
  if (debuggingOptions.buildInfo.isDebug || debuggingOptions.buildInfo.isProfile) {  
    observatoryUri = await observatoryDiscovery.uri;                                 
  }                                                                                  
                                                                                     
  return LaunchResult.succeeded(observatoryUri: observatoryUri);                     
} catch (error) {                                                                    
  printError('Error waiting for a debug connection: $error');                        
  return LaunchResult.failed();                                                      
} finally {                                                                          
  await observatoryDiscovery.cancel();                                               
}                                                                                    
```

> 生成的 uri 大概是这样：http://127.0.0.1:59199/zVaNpOWwTi0=/

### attach

在上面，我们会启动应用，同时使用 adb 转发设备端口到主机端口，然后我们会根据这个主机 URI 建立与 Dart VM 的 RPC 通信，这里使用的是 [json_rpc_2](https://github.com/dart-lang/json_rpc_2) 库。



#### connectToServiceProtocol

首先遍历每个 FlutterDevice，建立 RPC 连接：

``` dart
await device._connect(                  
  reloadSources: reloadSources,         
  restart: restart,                     
  compileExpression: compileExpression, 
);                                      
```

FlutterDevice 表示一个连接的设备，可以有多个，而 FlutterDevice 可以有多个 VMService，VMService 用于与 Dart VM 通信，VMService 将与 Dart VM 通信的操作封装在 VM 中，每个 VMService 都有持有一个 VM。

![VMService](https://user-gold-cdn.xitu.io/2019/9/5/16cff9e6f46b6839?w=690&h=488&f=png&s=8936)

调用 `VMService.connect()` 方法生成一个 VMService 对象，同时会建立 RPC 连接：

``` dart
final Uri wsUri = httpUri.replace(scheme: 'ws', path: fs.path.join(httpUri.path, 'ws'));              
final StreamChannel<String> channel = await _openChannel(wsUri, compression: compression);            
final rpc.Peer peer = rpc.Peer.withoutJson(jsonDocument.bind(channel));                               
final VMService service = VMService(peer, httpUri, wsUri, reloadSources, restart, compileExpression); 
// This call is to ensure we are able to establish a connection instead of                            
// keeping on trucking and failing farther down the process.                                          
await service._sendRequest('getVersion', const <String, dynamic>{});                                  
return service;                                                                                       
```

在 VMService 构造函数中，会生成 VM 对象，同时注册 **reloadSources** 等 RPC 方法处理函数：

``` dart
_vm = VM._empty(this);                                                            
_peer.listen().catchError(_connectionError.completeError);                        
                                                                                  
_peer.registerMethod('streamNotify', (rpc.Parameters event) {                     
  _handleStreamNotify(event.asMap);                                               
});                                                                               
                                                                                  
if (reloadSources != null) {                                                      
  _peer.registerMethod('reloadSources', (rpc.Parameters params) async {           
    final String isolateId = params['isolateId'].value;                           
    final bool force = params.asMap['force'] ?? false;                            
    final bool pause = params.asMap['pause'] ?? false;                            
                                                                                  
    if (isolateId is! String || isolateId.isEmpty)                                
      throw rpc.RpcException.invalidParams('Invalid \'isolateId\': $isolateId');  
    if (force is! bool)                                                           
      throw rpc.RpcException.invalidParams('Invalid \'force\': $force');          
    if (pause is! bool)                                                           
      throw rpc.RpcException.invalidParams('Invalid \'pause\': $pause');          
                                                                                  
    try {                                                                         
      await reloadSources(isolateId, force: force, pause: pause);                 
      return <String, String>{'type': 'Success'};                                 
    } on rpc.RpcException {                                                       
      rethrow;                                                                    
    } catch (e, st) {                                                             
      throw rpc.RpcException(rpc_error_code.SERVER_ERROR,                         
          'Error during Sources Reload: $e\n$st');                                
    }                                                                             
  });                                                                             
                                                                                  
  // If the Flutter Engine doesn't support service registration this will         
  // have no effect                                                               
  _peer.sendNotification('_registerService', <String, String>{                    
    'service': 'reloadSources',                                                   
    'alias': 'Flutter Tools',                                                     
  });                                                                             
}                                                                                 
```

建立连接成功后，会调用两个方法来进行初始化：`getVMs()` 和 `refreshViews()`：

`getVMs()` 最终会调用 `ServiceObject.reload()` 方法，`reload()` 函数会调用 `_fetchDirect()` 函数，VM 重载这个方法：

``` dart
@override                                                            
Future<Map<String, dynamic>> _fetchDirect() => invokeRpcRaw('getVM');
```

也就是说，调用 **getVM** 这个 RPC 方法，这个方法的结果返回 Dart VM 的全局信息。

```
class VM extends Response {
  // A name identifying this vm. Not guaranteed to be unique.
  string name;

  // Word length on target architecture (e.g. 32, 64).
  int architectureBits;

  // The CPU we are actually running on.
  string hostCPU;

  // The operating system we are running on.
  string operatingSystem;

  // The CPU we are generating code for.
  string targetCPU;

  // The Dart VM version string.
  string version;

  // The process id for the VM.
  int pid;

  // The time that the VM started in milliseconds since the epoch.
  //
  // Suitable to pass to DateTime.fromMillisecondsSinceEpoch.
  int startTime;

  // A list of isolates running in the VM.
  @Isolate[] isolates;
}
```

`refreshViews()` 函数最终会调用到 `VM.refreshViews()` 方法：

``` dart
Future<void> refreshViews({ bool waitForViews = false }) async {                                  
  assert(waitForViews != null);                                                                   
  assert(loaded);                                                                                 
  if (!isFlutterEngine)                                                                           
    return;                                                                                       
  int failCount = 0;                                                                              
  while (true) {                                                                                  
    _viewCache.clear();                                                                           
    // When the future returned by invokeRpc() below returns,                                     
    // the _viewCache will have been updated.                                                     
    // This message updates all the views of every isolate.                                       
    await vmService.vm.invokeRpc<ServiceObject>('_flutter.listViews');                            
    if (_viewCache.values.isNotEmpty || !waitForViews)                                            
      return;                                                                                     
    failCount += 1;                                                                               
    if (failCount == 5) // waited 200ms                                                           
      printStatus('Flutter is taking longer than expected to report its views. Still trying...'); 
    await Future<void>.delayed(const Duration(milliseconds: 50));                                 
    await reload();                                                                               
  }                                                                                               
}                                                                                                 
```

`refreshViews()` 会调用 **_flutter.listViews** RPC 方法，这个是 Flutter 在 Dart VM 上扩展的，具体可看：[Engine-specific-Service-Protocol-extensions](https://github.com/flutter/flutter/wiki/Engine-specific-Service-Protocol-extensions)。返回的响应为：

``` 
{
  "type": "FlutterViewList",
  "views": [
    {
      "type": "FlutterView",
      "id": "_flutterView/0x1066096d8",
      "isolate": {
        "type": "@Isolate",
        "fixedId": true,
        "id": "isolates/453229818",
        "name": "main.dart$main-453229818",
        "number": 453229818
      }
    }
  ]
}
```













