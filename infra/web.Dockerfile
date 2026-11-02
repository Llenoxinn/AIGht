FROM mcr.microsoft.com/dotnet/sdk:10.0.403 AS build
WORKDIR /source
COPY global.json ./
COPY src/AIGht.Web ./src/AIGht.Web
RUN dotnet restore src/AIGht.Web/AIGht.Web.csproj --locked-mode && dotnet publish src/AIGht.Web/AIGht.Web.csproj --no-restore -c Release -o /out
FROM nginx:stable-alpine
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out/wwwroot /usr/share/nginx/html
EXPOSE 80
