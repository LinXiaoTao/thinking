## 背景

在使用微信开源的 Matrix 项目中的 [matrix-trace-canary](https://github.com/Tencent/matrix/tree/master/matrix/matrix-android/matrix-trace-canary) 组件时，感觉有些不方便。matrix-trace-canary 使用 Gradle Plugin 在遍历类文件时，提前在特定方法中插入耗时统计代码：

``` java
// com.tencent.matrix.trace.MethodTracer.java
@Override                                                                                                       
protected void onMethodEnter() {                                                                                
    TraceMethod traceMethod = collectedMethodMap.get(methodName);                                               
    if (traceMethod != null) {                                                                                  
        traceMethodCount.incrementAndGet();                                                                     
        mv.visitLdcInsn(traceMethod.id);                                                                        
        mv.visitMethodInsn(INVOKESTATIC, TraceBuildConstants.MATRIX_TRACE_CLASS, "i", "(I)V", false);           
    }                                                                                                           
}

@Override                                                                                                                                   
protected void onMethodExit(int opcode) {                                                                                                   
    TraceMethod traceMethod = collectedMethodMap.get(methodName);                                                                           
    if (traceMethod != null) {                                                                                                              
        if (hasWindowFocusMethod && isActivityOrSubClass && isNeedTrace) {                                                                  
            TraceMethod windowFocusChangeMethod = TraceMethod.create(-1, Opcodes.ACC_PUBLIC, className,                                     
                    TraceBuildConstants.MATRIX_TRACE_ON_WINDOW_FOCUS_METHOD, TraceBuildConstants.MATRIX_TRACE_ON_WINDOW_FOCUS_METHOD_ARGS); 
            if (windowFocusChangeMethod.equals(traceMethod)) {                                                                              
                traceWindowFocusChangeMethod(mv, className);                                                                                
            }                                                                                                                               
        }                                                                                                                                   
                                                                                                                                            
        traceMethodCount.incrementAndGet();                                                                                                 
        mv.visitLdcInsn(traceMethod.id);                                                                                                    
        mv.visitMethodInsn(INVOKESTATIC, TraceBuildConstants.MATRIX_TRACE_CLASS, "o", "(I)V", false);                                       
    }                                                                                                                                       
}                                                                                                                                           
```

> `TraceBuildConstants.MATRIX_TRACE_CLASS` 即 `com/tencent/matrix/trace/core/AppMethodBeat`

也就是说，在原先的方法体的前和后各插入一段代码：

```java
AppMethodBeat.i(methodId);
// 原先的代码
AppMethodBeat.o(methodId);
```

这里 matrix-trace-canary 用的是 int 类型的 methodId 来代替方法名，这样的好处应该是为了节约内存，因为会缓存所有的 methodId，所以会提前声明一个数组来存储：

``` java
public static final int BUFFER_SIZE = 100 * 10000; // 7.6M
private static long[] sBuffer = new long[Constants.BUFFER_SIZE];
```

这里如果使用 String 来存储的话，所需要大小远远大于 7.6M。

但这带来一个问题，matrix-trace-canary 在慢函数检测打印堆栈时，会用这个 methodId 来标记实际的方法名。

```
0,1048574,1,11239
1,47,1,11237
2,53,1,11237
3,56,1,381
4,60,1,160
5,64,1,16
5,66,1,15
5,68,1,21
4,69,1,20
3,71,1,57
4,75,1,21
4,76,1,5
4,80,1,11
3,82,1,10001
```

所以 matrix-trace-canary 在插入统计代码时，会将这个映射表也输出来，默认为 build/outputs/mapping/*/methodMapping.txt：

```
1,0,sample.tencent.matrix.trace.TestFpsActivity$3 <init> (Lsample.tencent.matrix.trace.TestFpsActivity;Landroid.content.Context;I[Ljava.lang.Object;)V
2,1,sample.tencent.matrix.trace.TestTraceFragmentActivity <init> ()V
3,1,sample.tencent.matrix.listener.TestPluginListener <init> (Landroid.content.Context;)V
4,1,sample.tencent.matrix.trace.TestFpsActivity <init> ()V
5,0,sample.tencent.matrix.trace.TestFpsActivity$1 <init> (Lsample.tencent.matrix.trace.TestFpsActivity;)V
6,1,sample.tencent.matrix.trace.TestFpsActivity$2 doFrameAsync (Ljava.lang.String;JJIZ)V
7,1,sample.tencent.matrix.listener.TestPluginListener onReportIssue (Lcom.tencent.matrix.report.Issue;)V
8,1,sample.tencent.matrix.trace.TestFpsActivity$1 execute (Ljava.lang.Runnable;)V
9,4,sample.tencent.matrix.SplashActivity onCreate (Landroid.os.Bundle;)V
10,1,sample.tencent.matrix.trace.StartUpService onStartCommand (Landroid.content.Intent;II)I
11,1,sample.tencent.matrix.trace.StartUpBroadcastReceiver onReceive (Landroid.content.Context;Landroid.content.Intent;)V
12,1,sample.tencent.matrix.trace.FirstFragment onCreateView (Landroid.view.LayoutInflater;Landroid.view.ViewGroup;Landroid.os.Bundle;)Landroid.view.View;
...
```

## matrix-trace-processor

matrix-trace-processor 就是为了满足上面这个需求开发的，只要提供 matrix-trace-canary 生成的堆栈和 methodMapping.txt 文件，就能转化为实际的方法名，同时生成的是 DTrace 格式的堆栈文件，支持 stackcollapse 分析，也就是说可以转化成其他可视化格式，例如火焰图。

执行 `python3 main.py -h`：

``` usage: main.py [-h] {pull_traces,workflow_traces} ...
Matrix commandline utility!

positional arguments:
  {pull_traces,workflow_traces}
                        Supported features
    pull_traces         Pull traces from the device
    workflow_traces     Processing analysis traces

optional arguments:
  -h, --help            show this help message and exit
```

### pull_traces

支持从设备中拉取指定包名的堆栈文件，需要存放在内部存储 cache 目录，文件格式为 log。

> 即 Context.getCacheDir()

```
usage: main.py pull_traces [-h] (--last | --all | --count COUNT) package

positional arguments:
  package        Specify the package name using Matrix, e.g. com.foo.bar

optional arguments:
  -h, --help     show this help message and exit
  --last         Pull only the last trace
  --all          Pull all existing traces
  --count COUNT  Pull the last COUNT traces
```

例如，`python3 main.py pull_traces --last sample.tencent.matrix` 表示拉取包名为 sample.tencent.matrix 的最新更新的堆栈文件。

### workflow_traces

分析输出堆栈。

```
usage: main.py workflow_traces [-h] trace methodMapping

positional arguments:
  trace          Path to downloaded trace
  methodMapping  methodMapping

optional arguments:
  -h, --help     show this help message and exit
```

例如，`python3 main.py workflow_traces demo/1581129760409.log demo/methodMapping.txt > demo/1581129760409.txt`

1581129760409.txt 就是分析后生成的堆栈文件，我们可以使用 [FlameGraph](https://github.com/brendangregg/FlameGraph) 将它转化为火焰图。

1. 先使用 stackcollapse 生成 Fold stacks

   ``` shell
   ./stackcollapse.pl demo/1581129760409.txt > demo/1581129760409.folded
   ```

2. 使用 flamegraph 生成 SVG

   ``` shell
   ./flamegraph.pl demo/1581129760409.folded > demo/1581129760409.svg
   ```

最终效果如下：

![png](https://user-gold-cdn.xitu.io/2020/2/8/17023844b867fa2b?w=2392&h=368&f=png&s=151646)

## 源码

https://github.com/LinXiaoTao/matrix-trace-processor

## 感谢

[profilo](https://github.com/facebookincubator/profilo)

