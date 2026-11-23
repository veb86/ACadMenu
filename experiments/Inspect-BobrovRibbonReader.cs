#:property PublishAot=false

// Reads the CUIX macros and ribbon definitions through AutoCAD's managed CUI reader.
// Run with .NET 10 and the AutoCAD 2020–2024 AcCui.dll and AdWindows.dll in the same directory.
using System.Collections;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.Loader;
using System.Xml;
using System.Xml.Linq;
using System.Xml.Serialization;

if (args.Length != 2)
{
    Console.Error.WriteLine("Usage: dotnet run experiments/Inspect-BobrovRibbonReader.cs -- AcCui.dll BobrovMenu.cuix");
    return 2;
}

var library = Path.GetFullPath(args[0]);
var libraryDirectory = Path.GetDirectoryName(library)!;
var context = AssemblyLoadContext.Default;
context.Resolving += (loader, name) =>
{
    var path = Path.Combine(libraryDirectory, name.Name + ".dll");
    return File.Exists(path) ? loader.LoadFromAssemblyPath(path) : null;
};
var assembly = context.LoadFromAssemblyPath(library);
const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
const BindingFlags internalStatic = BindingFlags.Static | BindingFlags.NonPublic;
var readerType = FindType("CuiSerializationReader");
var init = typeof(XmlSerializationReader).GetMethod("Init", instance)!;
using var cuix = ZipFile.OpenRead(args[1]);
using var header = cuix.GetEntry("Header.cui")!.Open();
var version = XDocument.Load(header).Root!.Element("FileVersion")!;
var versionNumbers = new[] { "MajorVersion", "MinorVersion", "IncrementalVersion", "UserVersion" };
var versionType = FindType("FileVersion");
var constructor = versionType.GetConstructor(instance, [typeof(int), typeof(int), typeof(int), typeof(int)])!;
var fileVersion = constructor.Invoke(versionNumbers.Select(name => (object)(int)version.Attribute(name)!).ToArray());

// Set the file version and parsing state that the CUI loader supplies to its part readers.
FindType("CUIParser").GetField("currentFileVersion", internalStatic | BindingFlags.Public)!.SetValue(null, fileVersion);
FindType("CustomizationSection").GetProperty("IsParsing", internalStatic)!.SetValue(null, true);

foreach (var macro in Read("MenuGroup.cui", "Macro", "Read26_Macro", false, true))
    Print(macro, "Name", "Command", "CLICommand", "SmallImage", "LargeImage");

foreach (var tab in Read("RibbonRoot.cui", "RibbonTabSource", "Read_RibbonTabSource", false, true, null))
{
    Print(tab, "Text", "DefaultDisplay");
    foreach (var reference in Items(tab))
        Print(reference, "PanelId");
}

foreach (var panel in Read("RibbonRoot.cui", "RibbonPanelSource", "Read_RibbonPanelSource", false, true, null))
{
    Print(panel, "Text", "ElementID");
    foreach (var row in Items(panel).Where(item => item.GetType().Name == "RibbonRow"))
        foreach (var button in Items(row))
            Print(button, "Text", "MacroID", "ButtonStyle");
}
return 0;

Type FindType(string name) => assembly.GetType("Autodesk.AutoCAD.Customization." + name, throwOnError: true)!;
object? Property(object value, string name) => value.GetType().GetProperty(name, instance)!.GetValue(value);
IEnumerable<object> Items(object value) => ((IEnumerable)Property(value, "Items")!).Cast<object>();
void Print(object value, params string[] names) => Console.WriteLine(string.Join(" | ", names.Select(name => Property(value, name))));

IEnumerable<object> Read(string entry, string element, string method, params object?[] arguments)
{
    using var stream = cuix.GetEntry(entry)!.Open();
    using var xml = XmlReader.Create(stream);
    var read = readerType.GetMethod(method, instance)!;
    while (xml.ReadToFollowing(element))
    {
        var reader = Activator.CreateInstance(readerType, nonPublic: true)!;
        init.Invoke(reader, [xml, new XmlDeserializationEvents(), null]);
        yield return read.Invoke(reader, arguments)!;
    }
}
