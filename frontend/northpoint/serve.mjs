// Optional static preview. For authenticated local use, open the Docker site instead.
import http from 'node:http';
import fs from 'node:fs';
import './config.js';
const html=fs.readFileSync(new URL('./index.html',import.meta.url));
const port=Number(process.env.PORT||4173),host=process.env.HOST||'127.0.0.1';
http.createServer((request,response)=>{
 const pathname=new URL(request.url,'http://localhost').pathname;
 if(['/config.js','/northpoint/config.js'].includes(pathname)){response.writeHead(200,{'Content-Type':'text/javascript; charset=utf-8','Cache-Control':'no-store'});response.end(fs.readFileSync(new URL('./config.js',import.meta.url)));}
 else if(['/camera.html','/northpoint/camera.html'].includes(pathname)){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});response.end(fs.readFileSync(new URL('./camera.html',import.meta.url)));}
 else if(['/','/index.html','/northpoint/'].includes(pathname)){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});response.end(html);}
 else{response.writeHead(404);response.end('Not found');}
}).listen(port,host,()=>console.log(`Static preview: http://localhost:${port}/ (API settings: config.js). For sign-in, open ${new URL(globalThis.NORTHPOINT_CONFIG.BASE_URL).origin}/ through the backend server.`));
