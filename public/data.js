export const dataRoot = new URL('./data/', import.meta.url);
export function projectAsset(path) {
 const url = new URL(path, dataRoot);
 if (url.origin !== dataRoot.origin || !url.pathname.startsWith(dataRoot.pathname)) throw new Error('Некорректный путь выпуска');
 return url;
}
export async function jsonAsset(path) {
 const response = await fetch(projectAsset(path), {cache:'no-cache'});
 if (!response.ok) throw new Error('Не удалось загрузить ' + path);
 return response.json();
}
export const number = (n, digits=0) => Number(n).toLocaleString('ru-RU',{minimumFractionDigits:digits,maximumFractionDigits:digits});
export function element(tag,text,className) {
 const el=document.createElement(tag);if(text!==undefined) el.textContent=text;if(className) el.className=className;return el;
}
export function reportError(node,message) {
 node.hidden=false;node.replaceChildren(document.createTextNode(message+' '));
 const retry=element('button','Повторить');retry.addEventListener('click',()=>location.reload());node.append(retry);
}

